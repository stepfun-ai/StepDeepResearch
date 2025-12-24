/**
 * Search citation parsing utilities
 * Parse citation info from batch_search tool XML results
 */

import { CitationStore, QueryResult, SearchResultItem } from '../types/citation';

/**
 * Parse batch search results from XML string
 */
export function parseSearchResultsXML(xmlContent: string): CitationStore {
  const store: CitationStore = new Map();
  
  // Use regex to parse XML
  // Match each <item> block
  const itemRegex = /<item[^>]*>([\s\S]*?)<\/item>/g;
  let match;
  
  while ((match = itemRegex.exec(xmlContent)) !== null) {
    const itemContent = match[1];
    
    // Extract each field
    const citeIndex = extractXMLValue(itemContent, 'cite_index');
    const title = extractXMLValue(itemContent, 'title');
    const url = extractXMLValue(itemContent, 'url');
    const snippet = extractXMLValue(itemContent, 'snippet');
    
    if (citeIndex && url) {
      store.set(citeIndex, {
        cite_index: citeIndex,
        title: title || 'No Title',
        url: url,
        snippet: snippet,
      });
    }
  }
  
  return store;
}

/**
 * Extract tag value from XML content
 */
function extractXMLValue(content: string, tagName: string): string | undefined {
  const regex = new RegExp(`<${tagName}>([\\s\\S]*?)<\\/${tagName}>`, 'i');
  const match = content.match(regex);
  return match ? match[1].trim() : undefined;
}

/**
 * Check if content is batch search result
 */
export function isBatchSearchResult(content: string): boolean {
  return content.includes('<batch_search_results>') || 
         content.includes('<cite_index>web_');
}

/**
 * Extract all citations from tool call result
 */
export function extractCitationsFromToolResult(result: string): CitationStore {
  if (!isBatchSearchResult(result)) {
    return new Map();
  }
  return parseSearchResultsXML(result);
}

/**
 * Parse structured query results list (for search results panel display)
 */
export function parseQueryResults(xmlContent: string): QueryResult[] {
  const results: QueryResult[] = [];
  
  // Match each <query_result> block
  const queryResultRegex = /<query_result[^>]*>([\s\S]*?)<\/query_result>/g;
  let queryMatch;
  
  while ((queryMatch = queryResultRegex.exec(xmlContent)) !== null) {
    const queryContent = queryMatch[1];
    
    // Extract query metadata
    const query = extractXMLValue(queryContent, 'query') || '';
    const resultCountStr = extractXMLValue(queryContent, 'result_count');
    const resultCount = resultCountStr ? parseInt(resultCountStr, 10) : 0;
    
    // Extract all items
    const items: SearchResultItem[] = [];
    const itemRegex = /<item[^>]*>([\s\S]*?)<\/item>/g;
    let itemMatch;
    
    while ((itemMatch = itemRegex.exec(queryContent)) !== null) {
      const itemContent = itemMatch[1];
      
      const citeIndex = extractXMLValue(itemContent, 'cite_index');
      const title = extractXMLValue(itemContent, 'title');
      const url = extractXMLValue(itemContent, 'url');
      const site = extractXMLValue(itemContent, 'site');
      const publishedTime = extractXMLValue(itemContent, 'published_time');
      const snippet = extractXMLValue(itemContent, 'snippet');
      const content = extractXMLValue(itemContent, 'content');
      
      if (citeIndex && url) {
        items.push({
          cite_index: citeIndex,
          title: title || 'No Title',
          url,
          site,
          published_time: publishedTime,
          snippet,
          content,
        });
      }
    }
    
    results.push({
      query,
      result_count: resultCount,
      items,
    });
  }
  
  return results;
}
