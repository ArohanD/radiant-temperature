#!/bin/bash
# Auto-discover every web/ inspector bundle under the repo (laptop pipeline +
# any pulled pod_runs/), generate a landing page that links to them all, and
# serve from the repo root on a single port. Click through to whichever run
# you want — no need to manage multiple http servers or remember paths.
#
# Usage (from repo root):
#   bash scripts/_serve_inspector.sh
#   open http://localhost:8765/outputs/inspector_index.html
#
# Override port: PORT=8767 bash scripts/_serve_inspector.sh

set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8765}"
INDEX="outputs/inspector_index.html"

mkdir -p outputs

# Find all web bundles. Two source patterns:
#   inputs/processed/<AOI>_baseline/web/index.html       (laptop pipeline output)
#   outputs/pod_runs/<AOI>_<timestamp>/web/index.html    (pulled pod runs)
mapfile -t bundles < <(
  find inputs/processed outputs/pod_runs -mindepth 3 -maxdepth 4 \
    -type f -name index.html -path '*/web/index.html' 2>/dev/null | sort
)

if [ "${#bundles[@]}" -eq 0 ]; then
  echo "No inspector bundles found."
  echo "Generate one with: ./env/bin/python scripts/_inspect_web.py"
  exit 1
fi

echo "Found ${#bundles[@]} inspector bundle(s). Building landing page..."

# Build the HTML. Each entry shows the source dir, last-modified time, and
# (when available) the headline.txt content as a short preview.
{
  cat <<'EOF'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SOLWEIG inspector — runs index</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 980px;
         margin: 2em auto; padding: 0 1em; color: #222; }
  h1 { border-bottom: 1px solid #ccc; padding-bottom: .3em; }
  .run { display: block; margin: .8em 0; padding: 1em 1.2em;
         border: 1px solid #ddd; border-radius: 6px; text-decoration: none;
         color: inherit; transition: background .15s, border-color .15s; }
  .run:hover { background: #f7f9fc; border-color: #4070a0; }
  .run-title { font-weight: 600; font-size: 1.05em; color: #2c5d8f; }
  .run-meta { color: #777; font-size: .85em; margin-top: .25em; }
  .run-headline { white-space: pre-wrap; font-family: ui-monospace, monospace;
                  font-size: .82em; background: #f4f4f4; padding: .6em .8em;
                  border-radius: 4px; margin-top: .6em; color: #444; }
  .badge { display: inline-block; padding: 2px 7px; font-size: .72em;
           border-radius: 10px; margin-left: .5em; vertical-align: middle; }
  .badge-laptop { background: #e6f3e6; color: #2a6b2a; }
  .badge-pod    { background: #e6efff; color: #2c5d8f; }
  footer { margin-top: 3em; color: #999; font-size: .8em; text-align: center; }
</style>
</head>
<body>
<h1>SOLWEIG inspector — runs</h1>
<p>Each card opens that run's 3D viewer. Source rasters are shared (canonical
inputs/processed/&lt;AOI&gt;_baseline/); SOLWEIG outputs differ per run.</p>
EOF

  for bundle in "${bundles[@]}"; do
    rundir=$(dirname "$(dirname "$bundle")")
    name=$(basename "$rundir")
    mtime=$(date -r "$bundle" '+%Y-%m-%d %H:%M')
    case "$rundir" in
      inputs/processed/*) badge='<span class="badge badge-laptop">laptop</span>' ;;
      outputs/pod_runs/*) badge='<span class="badge badge-pod">pod</span>' ;;
      *)                  badge='' ;;
    esac
    headline=""
    for h in "$rundir/figures/headline.txt" "$rundir/headline.txt" \
             "$(dirname "$rundir")/figures/headline.txt"; do
      [ -f "$h" ] && headline=$(<"$h") && break
    done
    headline_html=""
    if [ -n "$headline" ]; then
      esc=$(printf '%s' "$headline" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
      headline_html="<div class=\"run-headline\">$esc</div>"
    fi
    cat <<EOF
<a class="run" href="/$bundle">
  <div class="run-title">$name $badge</div>
  <div class="run-meta">$rundir · last updated $mtime</div>
  $headline_html
</a>
EOF
  done

  cat <<EOF
<footer>generated $(date '+%Y-%m-%d %H:%M:%S') by scripts/_serve_inspector.sh</footer>
</body></html>
EOF
} > "$INDEX"

echo "Wrote $INDEX"
echo
echo "Serving at http://localhost:$PORT/"
echo "  Landing page:  http://localhost:$PORT/$INDEX"
echo
echo "Ctrl-C to stop."
exec python -m http.server "$PORT"
