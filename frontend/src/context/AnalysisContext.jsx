// Holds the result of the most recent upload/analysis in memory so every
// page (Dashboard, Insights, Recommendations, Predictions history) reads
// from one source instead of re-fetching or duplicating upload logic.
import { createContext, useContext, useState } from 'react'

const AnalysisContext = createContext(null)

export function AnalysisProvider({ children }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  return (
    <AnalysisContext.Provider value={{ result, setResult, loading, setLoading }}>
      {children}
    </AnalysisContext.Provider>
  )
}

export function useAnalysis() {
  const ctx = useContext(AnalysisContext)
  if (!ctx) throw new Error('useAnalysis must be used within AnalysisProvider')
  return ctx
}
