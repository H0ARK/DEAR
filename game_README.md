# PyCollector Game

A simple 2D game where you collect items while avoiding obstacles, implemented in Python using Pygame.

## Game Overview

- **Goal**: Collect all the yellow circles (items) while avoiding the red diamonds (obstacles).
- **Controls**: Use arrow keys or WASD to move the blue square (player).
- **Win Condition**: Collect all items to win.
- **Lose Condition**: Touch any obstacle to lose.

## Installation

1. Make sure you have Python 3.12+ installed.
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

Or install Pygame directly:

```bash
pip install pygame
```

## How to Play

Run any of the following files:

```bash
# Run basic game setup:
python project_setup.py

# Run player movement demo:
python player_movement.py

# Run collectible items demo:
python collectible_items.py

# Run the complete game:
python complete_game.py
```

## Game Versions

1. **project_setup.py**: Basic game window setup with minimal functionality.
2. **player_movement.py**: Adds player movement with keyboard controls.
3. **collectible_items.py**: Adds collectible items and scoring.
4. **complete_game.py**: Full game with obstacles, win/lose conditions, and restart functionality.

## Controls

- **Arrow Keys** or **WASD**: Move the player
- **ESC**: Exit the game
- **R**: Restart the game (after winning or losing)

## Features

- Player character with smooth movement
- Collectible items that increase score
- Obstacles that cause game over when touched
- Score tracking
- Win and lose states with appropriate messages
- Simple and intuitive gameplay mechanics
- Boundary checking to keep the player within the screen
- Restart functionality 