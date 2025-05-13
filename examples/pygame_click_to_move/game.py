#!/usr/bin/env python3
# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import pygame
import sys
import math  # Needed for calculating distance and direction

# Initialize Pygame
pygame.init()

# Screen dimensions
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Pygame Click-to-Move")

# Colors
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLUE = (0, 0, 255)  # Color for target visualization

# Player properties
player_size = 30
player_x = SCREEN_WIDTH // 2
player_y = SCREEN_HEIGHT // 2
player_color = RED
player_speed = 5  # Pixels per frame

# Movement target
target_x = player_x
target_y = player_y
moving_to_target = False

# Game loop
running = True
clock = pygame.time.Clock()  # Create a clock object to control frame rate

while running:
    # Handle events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                target_x, target_y = event.pos
                moving_to_target = True

    # --- Movement Logic ---
    if moving_to_target:
        # Calculate the distance to the target
        distance = math.dist((player_x, player_y), (target_x, target_y))

        if distance > player_speed:
            # Calculate the direction vector
            dx = target_x - player_x
            dy = target_y - player_y
            angle = math.atan2(dy, dx)  # Angle in radians

            # Calculate movement vector
            move_x = player_speed * math.cos(angle)
            move_y = player_speed * math.sin(angle)

            # Update player position
            player_x += move_x
            player_y += move_y
        else:
            # Player is close enough, snap to target
            player_x = target_x
            player_y = target_y
            moving_to_target = False  # Stop moving

    # --- Drawing ---
    screen.fill(WHITE)  # Fill the background

    # Draw target (optional, for visualization)
    if moving_to_target:
        pygame.draw.circle(screen, BLUE, (int(target_x), int(target_y)), 5)

    # Draw player
    # We draw the player centered on its coordinates for better movement feel
    player_rect = pygame.Rect(
        int(player_x - player_size // 2),
        int(player_y - player_size // 2),
        player_size,
        player_size
    )
    pygame.draw.rect(screen, player_color, player_rect)

    # Update the display
    pygame.display.flip()
    
    # Control frame rate
    clock.tick(60)  # 60 FPS

# Quit Pygame
pygame.quit()
sys.exit()
