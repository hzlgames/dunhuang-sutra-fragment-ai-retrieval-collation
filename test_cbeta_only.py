from src.cbeta_search import CBETASearcher

def test_cbeta():
    searcher = CBETASearcher()
    query = "一切有为法"
    print(f"Testing CBETA search with query: {query}")
    
    # Test similar search
    results = searcher.search_similar(query)
    print(f"Found {len(results)} results.")
    for res in results[:3]:
        print(res)

    # Test save
    if results:
        searcher.save_results_to_file(results, "test_cbeta_output.txt")

if __name__ == "__main__":
    test_cbeta()
