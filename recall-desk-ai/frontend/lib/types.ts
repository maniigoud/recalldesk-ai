export type Status = 'Open' | 'Investigating' | 'Waiting' | 'Resolved' | 'Escalated'
export type Priority = 'Low' | 'Medium' | 'High' | 'Critical'
export type MemoryType = 'Fact' | 'Experience' | 'Preference' | 'Relationship' | 'Resolution'
export interface User { id: string; name: string; email: string; role: string }
export interface Customer { id: string; name: string; company: string; email: string; status: 'Active' | 'At risk' | 'Paused'; since: string; agent: string; openTickets: number; memories: number; lastInteraction: string; environment: string[]; preferences: string[] }
export interface Ticket { id: string; customerId: string; customer: string; company: string; title: string; priority: Priority; status: Status; agent: string; updated: string; created: string }
export interface TicketMessage { id: string; author: string; role: 'customer' | 'agent'; content: string; timestamp: string }
export interface Conversation { id: string; customerId: string; ticketId?: string; messages: TicketMessage[] }
export interface Memory { id: string; type: MemoryType; content: string; customerId: string; customer: string; context: string; remembered: string; lastRecalled: string; source: string; confidence: number }
export interface Resolution { id: string; title: string; detail: string; customerId: string; date: string }
export interface AgentMessage { id: string; role: 'user' | 'assistant' | 'system'; content: string; timestamp: string; recalled?: boolean }
export interface Analytics { label: string; value: number; change?: string }
export interface AuthState { user: User | null; demo: boolean }
export interface SearchResult { kind: 'Customer' | 'Ticket' | 'Memory'; title: string; subtitle: string; href: string }
export const navItems = [{ label: 'Dashboard', href: '/dashboard' }, { label: 'Customers', href: '/customers' }, { label: 'Tickets', href: '/tickets' }, { label: 'AI Support', href: '/support' }, { label: 'Memory Explorer', href: '/memory' }, { label: 'Analytics', href: '/analytics' }, { label: 'Settings', href: '/settings' }]
