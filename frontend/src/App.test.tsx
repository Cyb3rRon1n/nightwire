import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the nightwire title', () => {
    render(<App />)
    expect(screen.getByText(/nightwire/i)).toBeInTheDocument()
  })
})
