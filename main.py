import game_interface
import states


if __name__ == '__main__':
    interface = game_interface.GameInterface()
    interface.push(states.InGameState(interface))
    interface.run()
