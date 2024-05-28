import lightning.pytorch as pl
import torch
import math
import copy
from torch.optim import Adam

from lightning import Callback
from rl4co import utils
import random
log = utils.get_pylogger(__name__)


class ReptileCallback(Callback):

    # Meta training framework for addressing the generalization issue
    # Based on Zhou et al. (2023): https://arxiv.org/abs/2305.19587
    def __init__(self,
                 num_tasks,
                 alpha,
                 alpha_decay,
                 min_size,
                 max_size,
                 sch_bar = 0.9,
                 data_type = "size",
                 print_log=True):
        super().__init__()

        self.num_tasks = num_tasks # i.e., B in the paper
        self.alpha = alpha
        self.alpha_decay = alpha_decay
        self.sch_bar = sch_bar
        self.print_log = print_log
        if data_type == "size":
            self.task_set = [(n,) for n in range(min_size, max_size + 1)]
        else:
            raise NotImplementedError

    def on_fit_start(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:

        # Sample a batch of tasks
        self._sample_task()
        self.selected_tasks[0] = (pl_module.env.generator.num_loc, )

    def on_train_epoch_start(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:

        # Alpha scheduler (decay for the update of meta model)
        self._alpha_scheduler()

        # Reinitialize the task model with the parameters of the meta model
        if trainer.current_epoch %  self.num_tasks == 0: # Save the meta model
            self.meta_model_state_dict = copy.deepcopy(pl_module.state_dict())
            self.task_models = []
            # Print sampled tasks
            if self.print_log:
                print('\n>> Meta epoch: {} (Exact epoch: {}), Training task: {}'.format(trainer.current_epoch//self.num_tasks, trainer.current_epoch, self.selected_tasks))
        else:
            pl_module.load_state_dict(self.meta_model_state_dict)

        # Reinitialize the optimizer every epoch
        lr_decay = 0.1 if trainer.current_epoch+1 == int(self.sch_bar * trainer.max_epochs) else 1
        old_lr  = trainer.optimizers[0].param_groups[0]['lr']
        new_optimizer = Adam(pl_module.parameters(), lr=old_lr * lr_decay)
        trainer.optimizers = [new_optimizer]

        # Print
        if self.print_log:
            if hasattr(pl_module.env.generator, 'capacity'):
                print('\n>> Training task: {}, capacity: {}'.format(pl_module.env.generator.num_loc, pl_module.env.generator.capacity))
            else:
                print('\n>> Training task: {}'.format(pl_module.env.generator.num_loc))

    def on_train_epoch_end(self,  trainer: pl.Trainer, pl_module: pl.LightningModule):

        # Save the task model
        self.task_models.append(copy.deepcopy(pl_module.state_dict()))
        if (trainer.current_epoch+1) % self.num_tasks == 0:
            # Outer-loop optimization (update the meta model with the parameters of the task model)
            with torch.no_grad():
                state_dict = {params_key: (self.meta_model_state_dict[params_key] +
                                           self.alpha * torch.mean(torch.stack([fast_weight[params_key] - self.meta_model_state_dict[params_key]
                                                                                for fast_weight in self.task_models], dim=0).float(), dim=0))
                              for params_key in self.meta_model_state_dict}
                pl_module.load_state_dict(state_dict)

        # Get ready for the next meta-training iteration
        if (trainer.current_epoch + 1) % self.num_tasks == 0:
            # Sample a batch of tasks
            self._sample_task()

        # Load new training task (Update the environment)
        self._load_task(pl_module, task_idx = (trainer.current_epoch+1) % self.num_tasks)

    def _sample_task(self):
        # Sample a batch of tasks
        w, self.selected_tasks = [1.0] * self.num_tasks, []
        for b in range(self.num_tasks):
            task_params = random.sample(self.task_set, 1)[0]
            self.selected_tasks.append(task_params)
        self.w = torch.softmax(torch.Tensor(w), dim=0)

    def _load_task(self, pl_module: pl.LightningModule, task_idx=0):
        # Load new training task (Update the environment)
        task_params, task_w = self.selected_tasks[task_idx], self.w[task_idx].item()
        pl_module.env.generator.num_loc = task_params[0]
        if hasattr(pl_module.env.generator, 'capacity'):
            task_capacity = math.ceil(30 + task_params[0] / 5) if task_params[0] >= 20 else 20
            pl_module.env.generator.capacity = task_capacity

    def _alpha_scheduler(self):
        self.alpha = max(self.alpha * self.alpha_decay, 0.0001)

