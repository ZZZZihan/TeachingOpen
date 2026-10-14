# -*- coding: utf-8 -*-
# 缤纷雪花 / Colourful Snowflakes
# Original: Carrie Anne Philbin / Geek Gurl Diaries and Raspberry Pi Foundation.
# Source: https://github.com/raspberrypilearning/turtle-snowflakes/blob/master/code/snowflake.py
# Original video: https://www.youtube.com/watch?v=DHmeX7YTHBY
# Upstream commit: e80a75fdcbc35b94bf20c52b064aec54a6716d78
# Licence: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
# Adapted for TeachingOpen: retains functions and eight repeated branches;
# redraws the branch symmetrically, with a composed layout, new palette,
# bounded loops, paced updates, captions and no exitonclick requirement.
# Adaptation licence: CC BY-SA 4.0. Original authorship is retained.

from turtle import Turtle, Screen
import time

print("Original: Carrie Anne Philbin / Geek Gurl Diaries + Raspberry Pi Foundation")
print("Source: https://github.com/raspberrypilearning/turtle-snowflakes/blob/master/code/snowflake.py")
print("Original video: https://www.youtube.com/watch?v=DHmeX7YTHBY")
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

def caption(y, words, colour, size):
    pen.goto(0, y)
    pen.color(colour)
    pen.write(words, False, "center", ("Arial", size, "normal"))

caption(146, "COLOURFUL SNOWFLAKES", "#f1f5ff", 18)
caption(125, "Eight branches make one tiny winter universe.", "#a5b8df", 9)
caption(-148, "Original: Carrie Anne Philbin / Geek Gurl Diaries", "#a5b8df", 8)
caption(-164, "+ Raspberry Pi Foundation  |  CC BY-SA 4.0", "#a5b8df", 8)

def branch(length):
    # Each third of a branch carries two small twigs.
    for twig in range(3):
        pen.forward(length / 3.0)
        pen.left(45)
        pen.forward(length / 4.0)
        pen.backward(length / 4.0)
        pen.right(90)
        pen.forward(length / 4.0)
        pen.backward(length / 4.0)
        pen.left(45)
    pen.backward(length)

def snowflake(x, y, length, colour):
    pen.penup()
    pen.goto(x, y)
    pen.color(colour)
    pen.pensize(2)
    pen.pendown()
    for arm in range(8):
        pen.setheading(arm * 45)
        branch(length)
        screen.update()
        # Pacing also keeps the browser's drawing request limit comfortable.
        time.sleep(0.10)
    pen.penup()
    pen.goto(x, y)
    pen.dot(5, colour)

# The fixed arrangement keeps every snowflake inside the small canvas.
snowflakes = [(-137, 58, 33, "#82e0f2"),
              (135, 54, 40, "#d1a0ff"),
              (0, 3, 67, "#f6fbff"),
              (-139, -78, 28, "#ffbdc9"),
              (133, -79, 31, "#a7edca"),
              (0, -110, 21, "#ffe49b")]

for x, y, length, colour in snowflakes:
    snowflake(x, y, length, colour)

screen.update()
print("Finished. Change a position, length or colour in the snowflakes list and run again.")
