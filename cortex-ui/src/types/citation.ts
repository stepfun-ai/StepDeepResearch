/**
 * Search citation related type definitions
 */

// Single search result item
export interface SearchResultItem {
  cite_index: string;  // Citation index, e.g., web_bb7e2cd7
  title: string;
  url: string;
  site?: string;
  published_time?: string;
  snippet?: string;
  content?: string;
}

// Search results for a single query
export interface QueryResult {
  query: string;
  result_count: number;
  items: SearchResultItem[];
}

// Batch search results
export interface BatchSearchResults {
  total_queries: number;
  total_items: number;
  query_results: QueryResult[];
}

// Citation info (simplified, for rendering citations)
export interface CitationInfo {
  cite_index: string;
  title: string;
  url: string;
  snippet?: string;
}

// Citation store type
export type CitationStore = Map<string, CitationInfo>;
