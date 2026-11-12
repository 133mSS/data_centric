"""Compatibility launcher; measurements use the public RAG entry points."""
def main():
    # Lazy import prevents pytest collection from importing runtime DB dependencies.
    from answer_leakage_test_public_entrypoints import main as run_benchmark
    run_benchmark()

if __name__ == "__main__":
    main()
