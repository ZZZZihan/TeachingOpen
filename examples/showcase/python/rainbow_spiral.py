# -*- coding: utf-8 -*-
# 彩虹螺旋 / Rainbow Spiral
# Original tutorial: Turtley Amazing, Raspberry Pi Foundation.
# Source: https://projects.raspberrypi.org/en/projects/turtley-amazing/0
# Repository: https://github.com/raspberrypilearning/turtley-amazing
# Upstream commit: 016d7f426489921e47b31a486b78abe7ce4b3e5f
# Licence: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
# Adapted for TeachingOpen: a growing spiral based on the tutorial's loops,
# turns and repeating colour list. New layout, palette, timing and captions.
# This is an adaptation of the tutorial, not its Hello World starter file.
# Adaptation licence: CC BY-SA 4.0. Original authorship is retained.

from turtle import Turtle, Screen
import time

print("Original: Turtley Amazing - Raspberry Pi Foundation")
print("Source: https://projects.raspberrypi.org/en/projects/turtley-amazing/0")
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

caption(146, "RAINBOW SPIRAL", "#f1f5ff", 18)
caption(125, "One loop. Seven colours. Endless possibilities.", "#a5b8df", 9)
caption(-154, "Original: Raspberry Pi Foundation  |  CC BY-SA 4.0", "#a5b8df", 8)

# A list and the modulo operator let the colours repeat in order.
colours = ["#ff6d9d", "#ffb86b", "#ffe58a", "#6ee7bd",
           "#68d9ef", "#8b9cff", "#cb9cff"]
pen.goto(0, 0)
pen.setheading(0)
pen.pensize(2)
pen.pendown()

# Try changing 91 to 89, or changing 120 to a smaller number.
# A finite loop completes safely and can be run again.
for step in range(120):
    pen.color(colours[step % len(colours)])
    pen.forward(2 + step * 1.45)
    pen.right(91)
    if step % 6 == 5:
        screen.update()
        time.sleep(0.06)

screen.update()
print("Finished. Try changing the turn angle or the colour list, then run again.")
