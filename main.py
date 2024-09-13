import os

import game_interface
import states
import consts


if __name__ == '__main__':
    os.chdir(consts.GAME_PATH)
    interface = game_interface.GameInterface()
    interface.push(states.InGameState(interface))
    interface.run()
