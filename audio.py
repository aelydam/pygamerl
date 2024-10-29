import actions

ACTION_SFX: dict[type[actions.Action], str] = {
    actions.AttackAction: "hit",
    actions.Use: "powerUp",
    actions.MoveAction: "click",
    actions.ToggleDoor: "door",
    actions.ToggleTorch: "click",
    actions.Die: "break",
    actions.Heal: "heal",
    actions.Pickup: "pickup",
    actions.LevelUp: "powerUp",
}
