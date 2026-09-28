// Rule probe only. This does not change or benchmark the external engine.
package main

import (
    "encoding/json"
    "os"
    "strings"
    "splendor/engine"
)

func main() {
    game := engine.NewRandomGame(2)
    game.Bank = engine.NewTokenWallet(0, 0)
    illegalTakes := 0
    var first engine.Move
    for _, move := range game.Moves() {
        if strings.HasPrefix(move.String(), "get ") {
            illegalTakes++
            if first == nil { first = move }
        }
    }
    report := map[string]any{"engine": "averagestardust", "workload": "rule_probe", "bank_all_zero": true, "illegal_take_actions": illegalTakes, "whole_game_comparable": false}
    if first != nil {
        after := first.Apply(game, false)
        report["selected_move"] = first.String()
        report["bank_after"] = after.Bank
    }
    if err := json.NewEncoder(os.Stdout).Encode(report); err != nil { panic(err) }
    if illegalTakes == 0 { os.Exit(3) }
}
