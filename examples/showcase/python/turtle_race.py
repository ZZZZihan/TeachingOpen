# -*- coding: utf-8 -*-
# 海龟赛跑 / Turtle Race
# Original tutorial and code: Raspberry Pi Foundation.
# Source: https://github.com/raspberrypilearning/turtle-race/blob/master/en/resources/turtle-race-finished-turtle-race.py
# Tutorial: https://projects.raspberrypi.org/en/projects/turtle-race
# Upstream commit: 8aa4a42fa3cc7460e00776c7d1bcb8818a5b7f21
# Licence: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
# Adapted for TeachingOpen: retains four turtles and random forward steps;
# adds a bounded race, finish detection, a winner, a compact track, new
# palette, captions and paced updates. No external assets or dependencies.
# Adaptation licence: CC BY-SA 4.0. Original authorship is retained.

from turtle import Turtle, Screen
from random import randint
import time

print("Original: Turtle Race - Raspberry Pi Foundation")
print("Source: https://github.com/raspberrypilearning/turtle-race/blob/master/en/resources/turtle-race-finished-turtle-race.py")
print("Licence: CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/")

screen = Screen()
# Keep the design proportional when the player is wider or smaller.
canvas_width = screen.window_width()
canvas_height = screen.window_height()
scale = min(canvas_width / 480.0, canvas_height / 360.0)
screen.setworldcoordinates(-canvas_width / (2 * scale),
                          -canvas_height / (2 * scale),
                          canvas_width / (2 * scale),
                          canvas_height / (2 * scale))
screen.bgcolor("#111b36")
screen.tracer(0, 0)

pen = Turtle()
pen.speed(0)
pen.hideturtle()
pen.penup()

def label(x, y, words, colour, size, align="center"):
    pen.penup()
    pen.goto(x, y)
    pen.color(colour)
    pen.write(words, False, align, ("Arial", size, "normal"))

def line(x1, y1, x2, y2, colour, width):
    pen.penup()
    pen.goto(x1, y1)
    pen.color(colour)
    pen.pensize(width)
    pen.pendown()
    pen.goto(x2, y2)
    pen.penup()

label(0, 146, "TURTLE RACE", "#f1f5ff", 18)
label(0, 125, "Pick your colour. Who will cross the finish line first?", "#a5b8df", 9)
label(-165, 94, "START", "#a5b8df", 8)
label(165, 94, "FINISH", "#a5b8df", 8)
label(0, -162, "Original: Raspberry Pi Foundation  |  CC BY-SA 4.0", "#a5b8df", 8)

start_x = -165
finish_x = 165
lanes = [65, 20, -25, -70]
colours = ["#ff7fa3", "#70dbed", "#b99aff", "#f5d77f"]
names = ["ROSE", "AQUA", "VIOLET", "GOLD"]

for y in [87, 42, -3, -48, -93]:
    line(-190, y, 192, y, "#344463", 1)

# A dashed finish is made from small line segments, with no image file.
for y in range(-90, 90, 12):
    line(finish_x, y, finish_x, y + 6, "#edf3ff", 3)
    if y % 36 == 18:
        screen.update()
        time.sleep(0.08)

racers = []
positions = [start_x, start_x, start_x, start_x]
for index in range(4):
    racer = Turtle()
    racer.speed(0)
    racer.shape("turtle")
    racer.color(colours[index])
    racer.penup()
    racer.goto(start_x, lanes[index])
    racer.setheading(0)
    racer.pensize(2)
    racer.pendown()
    racers.append(racer)
    label(-198, lanes[index] - 5, str(index + 1), colours[index], 10)
    screen.update()
    time.sleep(0.10)

winner = -1
finished = 0

# Even the smallest step finishes in 66 rounds; the 80-round bound is ample.
# Each turtle stops exactly on the finish line. Run again for a new race.
for turn in range(80):
    for index in range(4):
        if positions[index] < finish_x:
            step = min(randint(5, 11), finish_x - positions[index])
            racers[index].forward(step)
            positions[index] += step
            if positions[index] == finish_x:
                finished += 1
                if winner == -1:
                    winner = index
    screen.update()
    time.sleep(0.04)
    if finished == 4:
        break

label(0, -126, names[winner] + " WINS!", colours[winner], 16)
label(0, -145, "Run again for another race.", "#a5b8df", 9)
screen.update()
print(names[winner] + " wins! Run again for a new race.")
