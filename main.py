import os

import consts
import game_interface
import keybinds  # must be here to avoid circular import
import states

if __name__ == "__main__":
    os.chdir(consts.GAME_PATH)
    interface = game_interface.GameInterface()
    interface.push(states.TitleState(interface))
    interface.run()
