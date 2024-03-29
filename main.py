import argparse
import os
import torch
import numpy as np
from gym import spaces
from tensorboardX import SummaryWriter
from collections import deque

from utils.envbuilder import build_env, set_global_seeds
from utils.vecenv import space_dim
import agents
from agents.PPO import run_ppo_train
from agents.PG import run_pg_train
from agents.NPG import run_npg_train
from agents.TRPO import run_trpo_train
from agents.NAF import run_naf_train
from agents.DDPG import run_ddpg_train
from agents.TD3 import run_td3_train
from agents.HTRPO import run_htrpo_train
from agents.config import *
from configs import NAF_Reacherv2, NAF_Pendulumv0, AdaptiveKLPPO_Hopperv2, \
    AdaptiveKLPPO_Reacherv2, DDPG_Reacherv2, PG_Hopperv2, \
    PPO_Hopperv2, PPO_Reacherv2, TRPO_Swimmerv2, NPG_Hopperv2, \
    TRPO_BaxterReacherv0, TRPO_Hopperv2, TRPO_Walker2dv1, \
    DDPG_Swimmerv2, DDPG_Hopperv2, DDPG_Pendulumv0, HTRPO_FlipBit8, HTRPO_FlipBit16,\
    HTRPO_EmptyMaze, HTRPO_FourRoomMaze, HTRPO_FetchPushv1, HTRPO_FetchReachv1, \
    HTRPO_FetchSlidev1, HTRPO_FetchPushDiscrete, HTRPO_FetchPickAndPlacev1,\
    HTRPO_FetchReachDiscrete

torch.set_default_tensor_type(torch.FloatTensor)

def arg_parser():
    parser = argparse.ArgumentParser(description='PyTorch REINFORCE example')
    parser.add_argument('--alg', default='NAF',
                        help='algorithm to use: DQN | DDQN | DuelingDQN | DDPG | NAF | PG | NPG | TRPO | PPO')
    parser.add_argument('--env', default="Reacher-v1",
                        help='name of the environment to run')
    parser.add_argument('--ou_noise', type=bool, default=True)
    # TODO: SUPPORT PARAM NOISE
    parser.add_argument('--param_noise', type=bool, default=False)
    # TODO: SUPPORT NOISE END
    parser.add_argument('--exploration_end', type=int, default=100, metavar='N',
                        help='number of episodes with noise (default: 100)')
    parser.add_argument('--seed', type=int, default=4, metavar='N',
                        help='random seed (default: 4)')
    # TODO: add '--num_steps' '--num_episodes' '--updates_per_step' '--snapshot_episode' '--render' into config file.
    parser.add_argument('--num_envs', type=int, default=1, metavar='N',
                        help='env numbers (default: 1)')
    parser.add_argument('--num_steps', type=int, default=1e6, metavar='N',
                        help='max episode length (default: 1e6)')
    parser.add_argument('--network', default=None,
                        help='network type')
    parser.add_argument('--updates_per_step', type=int, default=1, metavar='N',
                        help='model updates per simulator step (default: 1)')
    parser.add_argument('--display', type=int, default=500, metavar='N',
                        help='episode interval for display (default: 5)')
    parser.add_argument('--eval_interval', type=int, default=0, metavar='N',
                        help='episode interval for display (default: 0)')
    parser.add_argument('--num_evals', type=int, default=10, metavar='N',
                        help='evaluation episode number each time (default: 10)')
    parser.add_argument('--snapshot_steps', type=int, default=1e4, metavar='N',
                        help='snapshot interval (default: 1e4)')
    parser.add_argument('--resume', action='store_true', default=False,
                        help='whether to resume training from a specific checkpoint')
    parser.add_argument('--unnormobs', action='store_true', default=False,
                        help='whether to normalize inputs')
    parser.add_argument('--unnormret', action='store_true', default=False,
                        help='whether to normalize outputs')
    parser.add_argument('--unnormact', action='store_true', default=False,
                        help='whether to normalize outputs')
    parser.add_argument('--checkpoint', type=int, default=0,
                        help='resume from this checkpoint')
    parser.add_argument('--render', type=float, default=0.,
                        help='when to render GUI (default: 0). WARNING: this is the episode return threshold which '
                             'controls when to render a GUI window, therefore, it should be set carefully with dif-'
                             'ferent environments and it will slow down the training process.')
    parser.add_argument('--test', help='test the specific policy.', action='store_true', default = False)
    parser.add_argument('--cpu', help='whether use cpu to train', action='store_true', default = False)

    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = arg_parser()

    configs = {}
    if args.alg in ("TD3", "NAF", "DDPG", "DQN", "DDQN", "DuelingDQN", "HTRPO"):
        print("The chosen alg is off-policy. Stored transitions are not normalized.")
        configs['norm_ob'] = not args.unnormobs
        configs['norm_rw'] = not args.unnormret
        args.unnormobs = True
        args.unnormret = True

    # build game environment
    env, env_type, env_id = build_env(args)
    env_obs_space = env.observation_space
    env_act_space = env.action_space
    # TODO: DEAL WITH DICT OBSERVATION SPACE, FOR EXAMPLE, IN TRPO OR DDPG.
    n_states = space_dim(env_obs_space)

    if isinstance(env_act_space, spaces.Discrete):
        n_actions = env_act_space.n  # decrete action space, value based rl brain
        n_action_dims = 1
        DICRETE_ACTION_SPACE = True
    elif isinstance(env_act_space, spaces.Box):
        n_actions = None
        n_action_dims = env_act_space.shape[0]
        DICRETE_ACTION_SPACE = False
    elif isinstance(env_act_space, np.ndarray):
        n_actions = len(env_act_space)
        n_action_dims = 1
        DICRETE_ACTION_SPACE = True
    else:
        assert 0, "Invalid Environment"

    # if env_type not in {"mujoco"}:
    #     print("The chosen env dose not support normalization. No normalization is applied.")
    #     configs['norm_ob'] = False
    #     configs['norm_rw'] = False

    logger = SummaryWriter(comment = args.alg + "-" + args.env)
    output_dir = os.path.join("output", "models", args.alg)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # initialize configurations
    if os.path.exists(os.path.join("configs", args.alg + "_" + "".join(args.env.split("-")) + '.py')):
        configs.update(eval(args.alg + "_" + "".join(args.env.split("-")) + "." + args.alg + "config"))
    configs['n_states'] = n_states
    configs['n_action_dims'] = n_action_dims
    configs['dicrete_action'] = DICRETE_ACTION_SPACE
    if n_actions:
        configs['n_actions'] = n_actions

    # for hindsight algorithms, init goal space of the environment.
    if args.alg in {"HTRPO"}:
        configs['other_data'] = env.reset()
        assert isinstance(configs['other_data'], dict), \
            "Please check the environment settings, hindsight algorithms only support goal conditioned tasks."
        del configs['other_data']['observation']
        configs['goal_space'] = env_obs_space.spaces['desired_goal']
        configs['env'] = env

    # init agent
    if args.alg in ("PG", "NPG", "TRPO", "PPO", "AdaptiveKLPPO", "HTRPO"):
        if DICRETE_ACTION_SPACE:
            RL_brain = eval("agents." + args.alg + "_Softmax(configs)")
        else:
            RL_brain = eval("agents." + args.alg + "_Gaussian(configs)")
    else:
        RL_brain = eval("agents." + args.alg + "(configs)")

    if not args.cpu:
        RL_brain.cuda()
    # resume networks
    if args.resume:
        RL_brain.load_model(load_path=output_dir, load_point=args.checkpoint)


    # training
    if args.alg == "PPO" or args.alg == "AdaptiveKLPPO":
        trained_brain = run_ppo_train(env, RL_brain, args.num_steps, logger)
    elif args.alg == "PG":
        trained_brain = run_pg_train(env, RL_brain, args.num_steps, logger)
    elif args.alg == "NPG":
        trained_brain = run_npg_train(env, RL_brain, args.num_steps, logger)
    elif args.alg == "TRPO":
        trained_brain = run_trpo_train(env, RL_brain, args.num_steps, logger)
    elif args.alg == "NAF":
        trained_brain = run_naf_train(env, RL_brain, args.num_steps, logger, args.display)
    elif args.alg == "DDPG":
        trained_brain = run_ddpg_train(env, RL_brain, args.num_steps, logger, args.display)
    elif args.alg == "TD3":
        trained_brain = run_td3_train(env, RL_brain, args.num_steps, logger, args.display)
    elif args.alg == 'HTRPO':
        trained_brain = run_htrpo_train(env, RL_brain, args.num_steps, logger,
                                        eval_interval = args.eval_interval if args.eval_interval > 0 else None,
                                        num_evals = args.num_evals)
    else:
        raise RuntimeError("Not an invalid algorithm.")

    logger.close()
