export interface CharacterSheet {
  player_id: string
  name: string
  role: string
  lifepath: string
  attributes: Record<string, number>
  health: number
  max_health: number
  armor: number
  conditions: string[]
  inventory: string[]
}

export interface RedactedCharacter {
  name: string
  role: string
  health: number
  max_health: number
  armor: number
  conditions: string[]
}

export interface StateView {
  type: 'state'
  session_id: string
  in_combat: boolean
  current_turn: string | null
  is_your_turn: boolean
  log: string[]
  location: string | null
  scene_mood: string | null
  active_objectives: string[]
  characters: Record<string, CharacterSheet | RedactedCharacter>
}

export interface ErrorMessage {
  type: 'error'
  message: string
}

export type ServerMessage = StateView | ErrorMessage

export function isErrorMessage(message: ServerMessage): message is ErrorMessage {
  return message.type === 'error'
}

export interface JoinMessage {
  type: 'join'
  character: {
    player_id: string
    name: string
    role: string
    lifepath: string
    attributes?: Record<string, number>
    health?: number
    max_health?: number
    armor?: number
    conditions?: string[]
    inventory?: string[]
  }
}

export interface ActionMessage {
  type: 'action'
  text: string
}

export interface StartCombatMessage {
  type: 'start_combat'
  initiative_rolls: Record<string, number>
}

export interface AdvanceTurnMessage {
  type: 'advance_turn'
}

export interface EndCombatMessage {
  type: 'end_combat'
}

export type ClientMessage =
  | JoinMessage
  | ActionMessage
  | StartCombatMessage
  | AdvanceTurnMessage
  | EndCombatMessage
