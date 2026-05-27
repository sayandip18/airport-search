import { useState, useEffect } from 'react'
import { useDebounce } from '../hooks/useDebounce'

interface Airport {
  id: string
  name: string
  icao_code: string | null
  iata_code: string
  municipality_name: string | null
  metro_name: string | null
  metro_code: string | null
  country_name: string | null
  country_code: string
  region_name: string | null
  region_code: string
}

export function AirportSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Airport[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const debouncedQuery = useDebounce(query, 300)

  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setResults([])
      setError(null)
      return
    }

    const controller = new AbortController()

    async function fetchAirports() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(
          `/api/airports/search?q=${encodeURIComponent(debouncedQuery)}&limit=10`,
          { signal: controller.signal },
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: Airport[] = await res.json()
        setResults(data)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError('Failed to fetch airports. Is the backend running?')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchAirports()
    return () => controller.abort()
  }, [debouncedQuery])

  return (
    <div className="search-wrapper">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by name, IATA/ICAO code, city, or country…"
        className="search-input"
        autoFocus
      />

      {loading && <p className="search-meta">Searching…</p>}
      {error && <p className="search-meta search-error">{error}</p>}
      {!loading && !error && debouncedQuery.trim() && results.length === 0 && (
        <p className="search-meta">No airports found for "{debouncedQuery}"</p>
      )}

      {results.length > 0 && (
        <ul className="results-list">
          {results.map((airport) => (
            <li key={airport.id} className="result-item">
              <div className="result-codes">
                <span className="badge">{airport.iata_code}</span>
                {airport.icao_code && (
                  <span className="badge badge-secondary">{airport.icao_code}</span>
                )}
              </div>
              <div className="result-body">
                <span className="result-name">{airport.name}</span>
                <span className="result-location">
                  {[airport.municipality_name, airport.country_name]
                    .filter(Boolean)
                    .join(', ')}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
