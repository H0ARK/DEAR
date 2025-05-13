# Pygame Click-to-Move Example

This example demonstrates a basic Pygame setup with a player character that can move using click-to-move mechanics similar to Diablo.

## Features

- Basic Pygame window setup
- Simple player character (red square)
- Click-to-move functionality
- Visual indicator for the target position

## Requirements

- Python 3.x
- Pygame

## Installation

1. Make sure you have Python installed
2. Install Pygame:

```bash
pip install pygame
```

## Running the Example

```bash
python game.py
```

## How to Play

- Click anywhere on the screen to move the player character to that position
- The player will move at a constant speed toward the clicked position
- A blue dot indicates the target position
- Close the window to exit the game

## Code Structure

The code is organized into the following sections:

1. Initialization: Sets up Pygame, creates the window, and defines colors and properties
2. Game Loop: Handles events, updates game state, and renders the screen
3. Event Handling: Detects mouse clicks and window close events
4. Movement Logic: Calculates direction and moves the player toward the target
5. Drawing: Renders the player and target indicator on the screen

## Extending the Example

You can extend this example by:

- Adding sprites instead of simple shapes
- Implementing obstacles and collision detection
- Adding animations for movement
- Implementing a more complex pathfinding algorithm
