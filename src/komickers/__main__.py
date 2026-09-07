from . import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborting...")
    except EOFError:
        print("\nAborting...")
