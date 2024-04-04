from typing import Union

from rl4co.envs.common.base import RL4COEnvBase
from rl4co.models.rl import PPO, REINFORCE
from rl4co.models.rl.reinforce.baselines import REINFORCEBaseline
from rl4co.models.zoo.common.decoder_only.policy import L2DPolicy


class L2DModel(PPO):
    def __init__(
        self,
        env: RL4COEnvBase,
        policy: L2DPolicy = None,
        policy_kwargs={},
        **kwargs,
    ):
        if policy is None:
            policy = L2DPolicy(env.name, **policy_kwargs)
        critic = None  # TODO DEFINE CRITIC
        super().__init__(env, policy, critic, **kwargs)


class L2DReinforce(REINFORCE):
    def __init__(
        self,
        env: RL4COEnvBase,
        policy: L2DPolicy = None,
        baseline: Union[REINFORCEBaseline, str] = "rollout",
        policy_kwargs={},
        baseline_kwargs={},
        **kwargs,
    ):
        if policy is None:
            policy = L2DPolicy(env.name, **policy_kwargs)

        super().__init__(env, policy, baseline, baseline_kwargs, **kwargs)
