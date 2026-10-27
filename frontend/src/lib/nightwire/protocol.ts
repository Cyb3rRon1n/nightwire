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
  portrait_path: string | null
  skills: Record<string, number>
  unspent_skill_points: number
  unspent_attribute_points: number
}

export interface RedactedCharacter {
  name: string
  role: string
  health: number
  max_health: number
  armor: number
  conditions: string[]
}

export interface PendingRoll {
  player_id: string
  attribute: string
  skill: string
  difficulty: 'easy' | 'moderate' | 'hard' | 'extreme'
  reason: string
  dc: number
  name: string
}

export interface RollResult extends PendingRoll {
  die_result: number
  attribute_mod: number
  skill_mod: number
  outcome: 'clean_success' | 'complication' | 'failure'
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
  pending_rolls: Record<string, PendingRoll>
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
    skills?: Record<string, number>
  }
}

export interface ActionMessage {
  type: 'action'
  text: string
}

export interface RollInitiativeMessage {
  type: 'roll_initiative'
}

export interface RollMessage {
  type: 'roll'
}

export interface AdvanceTurnMessage {
  type: 'advance_turn'
}

export interface EndCombatMessage {
  type: 'end_combat'
}

export interface ApproveCharacterMessage {
  type: 'approve_character'
  reference_photos?: string[]
}

export interface AllocateSkillPointsMessage {
  type: 'allocate_skill_points'
  skill: string
  amount: number
}

export interface AllocateAttributePointsMessage {
  type: 'allocate_attribute_points'
  attribute: string
  amount: number
}

export type ClientMessage =
  | JoinMessage
  | ActionMessage
  | RollInitiativeMessage
  | RollMessage
  | AdvanceTurnMessage
  | EndCombatMessage
  | ApproveCharacterMessage
  | AllocateSkillPointsMessage
  | AllocateAttributePointsMessage
