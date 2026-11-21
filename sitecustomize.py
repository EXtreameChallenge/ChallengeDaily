"""Install ChallengeDaily legacy module aliases for every Python process
started from the backend directory (including pytest and Electron spawns)."""
from legacy_aliases import install

install()
