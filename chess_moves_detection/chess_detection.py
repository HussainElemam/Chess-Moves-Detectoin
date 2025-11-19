#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chess movement detection and simple tracking using OpenCV.
Ports core logic from the provided C++ sample and adds --images support.

Dependencies:
  pip install opencv-python numpy

Notes:
- Finds inner 7x7 chessboard corners on an 8x8 board.
- Background subtraction triggers a "turn" when two contours persist.
- Mouse: double‑click a square to preview legal moves for that piece.
- Press Enter to accept detected corners in the Configuration step.
- Press Esc to exit at any time.
"""

import argparse
import glob
import os
from pathlib import Path
from dataclasses import dataclass
import cv2
import numpy as np

# ---------- constants (ported / filled) ----------
IMG_W = 960
IMG_H = 540

thresh_slider_max = 200
thresh_slider = 50
movementthreshold = 50   # trackbar‑controlled

C_INCR = 5               # movcount increment per frame when condition met

# piece ids; parity used for color (0 = black, 1 = white)
PAWN_B, PAWN_W   = 0, 1
KING_B, KING_W   = 2, 3
BISH_B, BISH_W   = 4, 5
QUEEN_B, QUEEN_W = 6, 7
KNIGHT_B, KNIGHT_W = 8, 9
ROOK_B, ROOK_W   = 10, 11

# ---------- global state (matches original structure) ----------
movcount = 0
turn = False  # display uses False=White, True=Black; capture logic treats True as "white moved"
drawPossibleMoves = False
pieceList = []           # list[Piece]
possiblePositions = []   # list[Position]
cornerlist = []          # list[(x,y)] 7x7
outputfile = "chess.txt"

# ---------- data types ----------
@dataclass
class Position:
    row: int
    column: int

@dataclass
class Piece:
    nr: int
    pos: Position

# ---------- utilities ----------
def on_trackbar(val):
    global movementthreshold
    movementthreshold = int(val)

def nrToString(nr: int) -> str:
    return {
        PAWN_B: "Black Pawn",  PAWN_W: "White Pawn",
        KING_B: "Black King",  KING_W: "White King",
        BISH_B: "Black Bishop",BISH_W: "White Bishop",
        QUEEN_B:"Black Queen", QUEEN_W:"White Queen",
        KNIGHT_B:"Black Knight",KNIGHT_W:"White Knight",
        ROOK_B: "Black Rook",  ROOK_W: "White Rook",
    }.get(nr, "")

def toFile(p: Piece, capture: bool):
    letters = ["a","b","c","d","e","f","g","h"]
    letter = {
        KING_W:"K", KING_B:"K",
        BISH_W:"B", BISH_B:"B",
        ROOK_W:"R", ROOK_B:"R",
        QUEEN_W:"Q", QUEEN_B:"Q",
        KNIGHT_W:"N", KNIGHT_B:"N",
    }.get(p.nr, "")
    with open(outputfile, "a", encoding="utf-8") as f:
        f.write(letter)
        if capture:
            f.write("x")
        # mirror column as original code did
        f.write(letters[7 - p.pos.column])
        f.write(str(p.pos.row))
        f.write("\n")

# ---------- chessboard geometry ----------
def findAllChessboardCorners(img_bgr):
    """Return list of 49 inner-corner points (x,y) or empty on failure."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, (7, 7))
    if not found:
        return []
    # refine
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001)
    cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    pts = corners.reshape(-1, 2).tolist()
    return pts

def coordToPosition(x: int, y: int, corners):
    """Map pixel (x,y) to board Position using corner grid logic from C++."""
    if not corners or len(corners) != 49:
        return Position(-1, -1)
    for j in range(len(corners)):
        cx, cy = corners[j]
        if x < cx and y < cy:
            return Position(row=j//7, column=j%7)
        if (j % 7) == 6 and y < cy and x > cx:
            return Position(row=j//7, column=7)
        if j > 41 and y > cy and x < cx:
            return Position(row=7, column=j%7)
        if j == 48 and y > cy and x > cx:
            return Position(row=7, column=7)
    return Position(-1, -1)

def positionToCoord(pos: Position):
    """Inverse mapping, only approximate for visual hints."""
    global cornerlist
    if not cornerlist or len(cornerlist) != 49:
        return (0, 0)
    x = int(cornerlist[6][0] + 10)
    y = int(cornerlist[42][1] + 10)
    for i in range(7):
        if pos.column == i:
            x = int(cornerlist[i][0] - 25)
        if pos.row == i:
            y = int(cornerlist[i*7][1] - 25)
    return (x, y)

# ---------- drawing ----------
def drawPoints(pointlist, img):
    global turn, drawPossibleMoves, possiblePositions
    for i, pt in enumerate(pointlist):
        x, y = int(pt[0]), int(pt[1])
        cv2.circle(img, (x, y), 3, (0, 255, 0), -1)
        cv2.putText(img, str(i), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1, cv2.LINE_AA)
    # show side to move (kept consistent with original display)
    txt = "White" if not turn else "Black"
    cv2.putText(img, txt, (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2, cv2.LINE_AA)

    if drawPossibleMoves:
        for pos in possiblePositions:
            cx, cy = positionToCoord(pos)
            cv2.circle(img, (int(cx), int(cy)), 10, (0, 0, 255), 2)

# ---------- piece / move helpers ----------
def initPieceList():
    global pieceList
    pieceList.clear()
    # white pawns
    for i in range(8):
        pieceList.append(Piece(PAWN_W, Position(1, i)))
    # black pawns
    for i in range(8):
        pieceList.append(Piece(PAWN_B, Position(6, i)))
    # rooks
    pieceList.append(Piece(ROOK_W, Position(0, 0)))
    pieceList.append(Piece(ROOK_W, Position(0, 7)))
    pieceList.append(Piece(ROOK_B, Position(7, 7)))
    pieceList.append(Piece(ROOK_B, Position(7, 0)))
    # knights
    pieceList.append(Piece(KNIGHT_W, Position(0, 1)))
    pieceList.append(Piece(KNIGHT_W, Position(0, 6)))
    pieceList.append(Piece(KNIGHT_B, Position(7, 6)))
    pieceList.append(Piece(KNIGHT_B, Position(7, 1)))
    # bishops
    pieceList.append(Piece(BISH_W, Position(0, 2)))
    pieceList.append(Piece(BISH_W, Position(0, 5)))
    pieceList.append(Piece(BISH_B, Position(7, 5)))
    pieceList.append(Piece(BISH_B, Position(7, 2)))
    # kings
    pieceList.append(Piece(KING_W, Position(0, 3)))
    pieceList.append(Piece(KING_B, Position(7, 3)))
    # queens
    pieceList.append(Piece(QUEEN_W, Position(0, 4)))
    pieceList.append(Piece(QUEEN_B, Position(7, 4)))

def findPieceOnPos(p: Position):
    """Return (found, piece, index)."""
    if p.column > 7 or p.column < 0 or p.row < 0 or p.row > 7:
        return False, None, -1
    for i, pc in enumerate(pieceList):
        if pc.pos.column == p.column and pc.pos.row == p.row:
            return True, pc, i
    return False, None, -1

def findLegalMoves(p: Piece):
    """Populate global possiblePositions for HUD circles."""
    global possiblePositions
    possiblePositions = []
    # pawns
    if p.nr in (PAWN_B, PAWN_W):
        rowoffset = -1 if p.nr == PAWN_B else 1
        front = Position(p.pos.row + rowoffset, p.pos.column)
        found, _, _ = findPieceOnPos(front)
        if not found and 0 <= front.row <= 7:
            possiblePositions.append(front)
            for dx in (-1, 1):
                diag = Position(p.pos.row + rowoffset, p.pos.column + dx)
                f2, other, _ = findPieceOnPos(diag)
                if f2 and other.nr % 2 != p.nr % 2:
                    possiblePositions.append(diag)
            if p.pos.row == 1 and p.nr == PAWN_W:
                front2 = Position(front.row + 1, front.column)
                f3, _, _ = findPieceOnPos(front2)
                if not f3:
                    possiblePositions.append(front2)
            if p.pos.row == 6 and p.nr == PAWN_B:
                front2 = Position(front.row - 1, front.column)
                f3, _, _ = findPieceOnPos(front2)
                if not f3:
                    possiblePositions.append(front2)
    # bishops and diagonals (also queen)
    if p.nr in (BISH_B, BISH_W, QUEEN_B, QUEEN_W):
        for dc in (-1, 1):
            for dr in (-1, 1):
                c = Position(p.pos.row, p.pos.column)
                cont = True
                while 0 < c.column < 7 and 0 < c.row < 7 and cont:
                    c = Position(c.row + dr, c.column + dc)
                    f, other, _ = findPieceOnPos(c)
                    if not f:
                        possiblePositions.append(c)
                    elif other.nr % 2 != p.nr % 2:
                        possiblePositions.append(c)
                        cont = False
                    else:
                        cont = False
    # rook straight lines (also queen)
    if p.nr in (ROOK_B, ROOK_W, QUEEN_B, QUEEN_W):
        # rows
        for dr in (-1, 1):
            c = Position(p.pos.row, p.pos.column)
            cont = True
            while 0 < c.row < 7 and cont:
                c = Position(c.row + dr, c.column)
                f, other, _ = findPieceOnPos(c)
                if not f:
                    possiblePositions.append(c)
                elif other.nr % 2 != p.nr % 2:
                    possiblePositions.append(c)
                    cont = False
                else:
                    cont = False
        # columns
        for dc in (-1, 1):
            c = Position(p.pos.row, p.pos.column)
            cont = True
            while 0 < c.column < 7 and cont:
                c = Position(c.row, c.column + dc)
                f, other, _ = findPieceOnPos(c)
                if not f:
                    possiblePositions.append(c)
                elif other.nr % 2 != p.nr % 2:
                    possiblePositions.append(c)
                    cont = False
                else:
                    cont = False
    # knights
    if p.nr in (KNIGHT_B, KNIGHT_W):
        for dr, dc in [(-2,-1), (-2,1), (-1,-2), (-1,2), (1,2), (1,-2), (2,1), (2,-1)]:
            c = Position(p.pos.row + dr, p.pos.column + dc)
            f, other, _ = findPieceOnPos(c)
            if 0 <= c.row <= 7 and 0 <= c.column <= 7 and (not f or other.nr % 2 != p.nr % 2):
                possiblePositions.append(c)
    # king
    if p.nr in (KING_B, KING_W):
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                c = Position(p.pos.row + dr, p.pos.column + dc)
                if 0 <= c.row <= 7 and 0 <= c.column <= 7:
                    f, other, _ = findPieceOnPos(c)
                    if not f or other.nr % 2 != p.nr % 2:
                        possiblePositions.append(c)

def findMovement(boundRectList, corners):
    """Identify from/to squares and update board + write notation."""
    global pieceList, turn
    print("Detecting Movement")
    poslist = []
    for (x, y, w, h) in boundRectList:
        cx = x + w//2
        cy = y + h//2
        p = coordToPosition(cx, cy, corners)
        poslist.append(p)
        print(f"Movement centre -> {p.column} {p.row}")

    if len(poslist) < 2:
        return

    posint = []
    pieceint = []
    colourint = []

    # check first location
    for i, pc in enumerate(pieceList):
        if pc.pos.row == poslist[0].row and pc.pos.column == poslist[0].column:
            print(nrToString(pc.nr), "was found")
            pieceint.append(i); posint.append(0); colourint.append(pc.nr % 2)
    # check second location
    for i, pc in enumerate(pieceList):
        if pc.pos.row == poslist[1].row and pc.pos.column == poslist[1].column:
            print(nrToString(pc.nr), "was found")
            pieceint.append(i); posint.append(1); colourint.append(pc.nr % 2)

    if len(posint) == 1:
        # one piece moved
        pieceList[pieceint[0]].pos = poslist[1 - posint[0]]
        print(nrToString(pieceList[pieceint[0]].nr), "moved to",
              poslist[1 - posint[0]].row, poslist[1 - posint[0]].column)
        toFile(pieceList[pieceint[0]], False)

    if len(posint) == 2:
        # capture. original code treats turn==True as "white moved"
        if turn:
            if colourint[0] == 1:
                mover = pieceint[0]; target = pieceint[1]; dest = poslist[1 - posint[0]]
            else:
                mover = pieceint[1]; target = pieceint[0]; dest = poslist[1 - posint[1]]
        else:
            if colourint[0] == 1:
                mover = pieceint[1]; target = pieceint[0]; dest = poslist[1 - posint[1]]
            else:
                mover = pieceint[0]; target = pieceint[1]; dest = poslist[1 - posint[0]]
        pieceList[mover].pos = dest
        print(nrToString(pieceList[mover].nr), "moved to", dest.row, dest.column, "and slayed", nrToString(pieceList[target].nr))
        pieceList[target].pos = Position(-1, -1)  # captured
        toFile(pieceList[mover], True)

# ---------- vision / detection ----------
def detectMovement(mask):
    """
    Apply threshold + morphology, find contours, update movcount and turn.
    Returns (movement_happened, rects, mask_vis)
    """
    global movcount, turn

    # binarize
    _, img = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
    # dilate
    element = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
    img = cv2.dilate(img, element, iterations=1)
    # contours
    cnts, _ = cv2.findContours(img.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    rects = [cv2.boundingRect(c) for c in cnts]
    # draw rects
    img_vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for (x, y, w, h) in rects:
        cv2.rectangle(img_vis, (x, y), (x+w, y+h), (255, 255, 255), 1)

    # movcount logic
    if len(cnts) == 2 or movcount < 0:
        movcount += C_INCR
    elif movcount > 0:
        movcount -= 1

    cv2.putText(img_vis, str(movcount), (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)

    moved = False
    if movcount > movementthreshold:
        movcount = -250
        turn = not turn
        moved = True
    return moved, rects, img_vis

# ---------- mouse ----------
def on_mouse(event, x, y, flags, userdata):
    global drawPossibleMoves, possiblePositions
    if event == cv2.EVENT_LBUTTONDBLCLK:
        possiblePositions = []
        pos = coordToPosition(x, y, cornerlist)
        print(f"Clicked at position {pos.row} {pos.column}")
        found, pc, _ = findPieceOnPos(pos)
        if found:
            print("Found piece", nrToString(pc.nr))
            findLegalMoves(pc)
            drawPossibleMoves = True
        else:
            print("No piece at this location!")
            drawPossibleMoves = False

# ---------- frame sources ----------
class FrameSource:
    """VideoCapture wrapper that also supports image sequences."""
    def __init__(self, video=None, cam=None, images=None):
        self.mode = None
        self.cap = None
        self.paths = None
        self.idx = 0

        if images:
            # accept directory or glob or single file
            if os.path.isdir(images):
                exts = ("*.jpg","*.jpeg","*.png","*.bmp","*.tif","*.tiff")
                paths = []
                for e in exts:
                    paths.extend(sorted(glob.glob(str(Path(images) / e))))
                self.paths = sorted(paths)
            else:
                self.paths = sorted(glob.glob(images))
            self.mode = "images"
            if not self.paths:
                raise FileNotFoundError(f"No images match: {images}")
        else:
            self.cap = cv2.VideoCapture(video if video is not None else int(cam if cam is not None else 0))
            if not self.cap.isOpened():
                raise RuntimeError("Cannot open file or videofeed")
            self.mode = "video"

    def read(self):
        if self.mode == "images":
            if self.idx >= len(self.paths):
                return False, None
            img = cv2.imread(self.paths[self.idx], cv2.IMREAD_COLOR)
            self.idx += 1
            return img is not None, img
        ret, frame = self.cap.read()
        return ret, frame

    def fps(self):
        if self.mode == "video":
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            return float(fps) if fps and fps > 0 else 0.0
        return 0.0

    def release(self):
        if self.cap is not None:
            self.cap.release()

# ---------- main ----------
def main():
    global cornerlist, outputfile, thresh_slider, movementthreshold

    ap = argparse.ArgumentParser(description="Chess movement detection (Python port)")
    ap.add_argument("--video", type=str, default=None, help="Path to video file")
    ap.add_argument("--cam", type=int, default=None, help="Webcam index")
    ap.add_argument("--images", type=str, default=None, help="Path to images dir or glob pattern or single file")
    ap.add_argument("--out", type=str, default="chess.txt", help="Moves output file")
    args = ap.parse_args()

    outputfile = args.out

    # init pieces
    initPieceList()
    for p in pieceList:
        print(p.pos.row, p.pos.column, p.nr)

    # source
    try:
        src = FrameSource(video=args.video, cam=args.cam, images=args.images)
    except Exception as e:
        print(str(e))
        return

    if src.mode == "video":
        print(f"{src.fps():.2f} frames per second")

    # --- configuration window: find corners and confirm ---
    windowname = "Configuration"
    cv2.namedWindow(windowname, cv2.WINDOW_NORMAL)
    while True:
        ok, frame = src.read()
        if not ok:
            print("End of stream during configuration")
            cv2.waitKey(0)
            return
        frame = cv2.resize(frame, (IMG_W, IMG_H))
        tilecorners = findAllChessboardCorners(frame)
        if tilecorners:
            cornerlist = tilecorners
        # draw found points and show
        drawPoints(tilecorners, frame)
        cv2.imshow(windowname, frame)
        key = cv2.waitKey(0) & 0xFF
        if key == 27:   # Esc
            return
        if key == 13:   # Enter
            print("Values saved")
            cv2.destroyWindow(windowname)
            break

    # --- main processing window ---
    windowname = "Chessmatch"
    cv2.namedWindow(windowname, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(windowname, on_mouse, None)
    cv2.createTrackbar("movement threshold", windowname, thresh_slider, thresh_slider_max, on_trackbar)

    bgdet = cv2.createBackgroundSubtractorMOG2()
    try:
        bgdet.setBackgroundRatio(0.5)  # available in cv2
    except Exception:
        pass
    element_erode = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    while True:
        ok, frame = src.read()
        if not ok:
            print("End of stream")
            cv2.waitKey(0)
            break
        frame = cv2.resize(frame, (IMG_W, IMG_H))

        fgmask = bgdet.apply(frame)
        bg = bgdet.getBackgroundImage()
        if bg is None:
            bg = np.zeros_like(frame)
        fgmask = cv2.erode(fgmask, element_erode, iterations=1)

        moved, rects, mask_vis = detectMovement(fgmask)
        if moved and cornerlist:
            # Rects are (x,y,w,h)
            findMovement(rects, cornerlist)

        # HUD
        disp = frame.copy()
        drawPoints(cornerlist, disp)

        # layout: frame | background | mask
        if bg.ndim == 2:
            bg_bgr = cv2.cvtColor(bg, cv2.COLOR_GRAY2BGR)
        else:
            bg_bgr = cv2.resize(bg, (IMG_W, IMG_H))
        mask_bgr = cv2.resize(mask_vis, (IMG_W, IMG_H))
        row = np.hstack([disp, bg_bgr, mask_bgr])
        cv2.imshow(windowname, row)

        key = cv2.waitKey(10) & 0xFF
        if key == 27:   # Esc
            break
        if key == 13:   # Enter
            print("End of capture")
            break

    src.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

