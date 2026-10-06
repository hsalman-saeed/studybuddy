try:
    import spaces

    @spaces.GPU
    def zerogpu_compatibility():
        pass
except ImportError:
    pass

from main import main

if __name__ == "__main__":
    main()

