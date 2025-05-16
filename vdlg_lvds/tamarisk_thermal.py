#!/usr/bin/env python3

import cv2
import numpy as np
import sys

""" Capture thermal information from tamarisk 640x480 thermal camera LVDS output and display to autovideosink """

def draw_val(img, text, pos, color):
    outline_col = (0,0,0)
    cv2.circle(img, pos, 6, outline_col, -1)
    cv2.circle(img, pos, 4, color,       -1)
    tw, th = cv2.getTextSize(text+'  ', cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
    x, y = pos
    h, w = img.shape[:2]
    offset_y = -th//2 if y > th else th # shift down if near top
    offset_x = -tw if x > (w-tw) else 0  # shift left if near right edge
    pos = (x + offset_x, y + offset_y)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, outline_col, 2, cv2.LINE_AA)
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color      , 1, cv2.LINE_AA)

def main():
    # Parse command line arguments if needed
    width, twidth, height = 640, 1280, 480

    cap = cv2.VideoCapture(f"gst-launch-1.0 v4l2src device=/dev/video-isi-csi1 ! video/x-raw,format=YUY2,width={twidth},height={height} ! appsink")
    out = cv2.VideoWriter("appsrc ! videoconvert ! autovideosink", 0, 25, (width, height), True)

    if not cap.isOpened():
        print("Cannot capture from camera. Exiting.")
        return

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert the frame from uint8 YU elements to big-endian uint16 format.
            np16 = frame.view(np.int16) # Convert uint8 elements to uint16 elements
            thermals = np16[:, width:]
            thermals.byteswap(inplace=True)
            # get values of interest
            avg = np.sum(thermals) / (width * height)
            tmax, tmin, tcen = np.max(thermals), np.min(thermals), int(thermals[height//2, width//2])
            # treat value as signed integer of 13 bits centered at 0C with 0.02C per lsb. So 0C = 4095
            tmax, tmin, tcen, avg = (p*0.02-81.92 for p in (tmax, tmin, tcen, avg))

            # convert to heatmap for display
            vis = cv2.normalize(thermals, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            color = cv2.applyColorMap(vis, cv2.COLORMAP_INFERNO)

            min_coord = np.unravel_index(np.argmin(thermals), thermals.shape)[::-1][1:]
            max_coord = np.unravel_index(np.argmax(thermals), thermals.shape)[::-1][1:]

            draw_val(color, f'avg: {avg:.1f}', (0, 0), (255,255,255))
            draw_val(color, f'  {tcen:.1f}', (width//2, height//2), (255,255,255))
            draw_val(color, f'  {tmax:.1f}', max_coord, (0,255,255))
            draw_val(color, f'  {tmin:.1f}', min_coord, (255,255,0))

            out.write(color)

            # Check for 'q' key press to exit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("\nExiting")
    finally:
        # Clean up resources
        cap.release()
        out.release()

if __name__ == "__main__":
    main()