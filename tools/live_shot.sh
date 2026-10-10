#!/usr/bin/env bash
# Save what a game started by tools/live_session.sh shows (the presenter's output, at the
# draw resolution scale) as DIR/shot.png, or as DIR/NAME.png when NAME is given.
#
# Usage: tools/live_shot.sh DIR [NAME]
#   Prints the PNG path, or "no shot" if none appears within 10 s (the game stopped
#   presenting). Needs Pillow.
set -u
DIR="$1"; NAME="${2:-shot}"
before=$(ls "$DIR"/forza_shot_*.ppm 2>/dev/null | wc -l)
touch "$DIR/shot.trigger"
for _ in $(seq 1 40); do
    [ "$(ls "$DIR"/forza_shot_*.ppm 2>/dev/null | wc -l)" -gt "$before" ] && break
    sleep 0.25
done
f=$(ls -t "$DIR"/forza_shot_*.ppm 2>/dev/null | head -1)
if [ "$(ls "$DIR"/forza_shot_*.ppm 2>/dev/null | wc -l)" -le "$before" ]; then
    rm -f "$DIR/shot.trigger"; echo "no shot"; exit 1
fi
python3 -c "from PIL import Image; Image.open('$f').save('$DIR/$NAME.png')" && rm -f "$f"
echo "$DIR/$NAME.png"
