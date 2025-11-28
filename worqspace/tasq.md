````markdown
# GOAL
Create a Python script that acts as a visual monitoring agent. It must read the output of a custom CLI command (`cstat`), parse the "gangsta-fied" Ceph cluster status, and render a live status dashboard onto a Divoom Pixoo-64 (64x64 pixel art display) via its local HTTP API.

# INPUT DATA (The "cstat" command)
The script will execute `cstat` (or read from stdin/mock for testing).
The output is a slang-translated version of standard Ceph status.
Here is a sample output:

```text
  wonqster:
    tag:     533c597a-6b12-11f0-b3a1-31f8187a0dc9
    vibe: AWW_YEAH
            (muted: POOL_NO_REDUNDANCY(2y))

  crew:
    lookouts: 3 daemons, circle kube0,kube1,kube2 (rollin 2w)
    capo: kube1.ujhekz(active, rollin 2w), bench: kube0.znwlma
    file-boss: 2/2 daemons up, 1 hot bench
    muscle: 5 osds: 5 up (since 2w), 5 in (since 2w)

  stash:
    vols: 1/1 minty
    stacks:   5 stacks, 305 chunkz
    objz: 32.23M objz, 25 TiB
    burn:   25 TiB burnt, 56 TiB / 81 TiB loose
    chunkz:      302 aight+allg00dYo
             3   aight+soapEm+deepdive

  flow:
    hustle:   474 KiB/s in, 13 KiB/s out, 141 op/s in, 4 op/s out
````

# PARSING LOGIC & MAPPINGS (Strict)

You must use Regex to extract values. Because the source uses a slang filter, you must map the specific slang terms back to their logical health states:

1.  **Health Status (`vibe`):**

      * **GREEN (OK):** Look for keyword `AWW_YEAH` (maps to HEALTH\_OK).
      * **ORANGE (WARN):** Look for keyword `OH_ShNAPP` (maps to HEALTH\_WARN).
      * **RED (CRIT):** Look for keyword `OH_n000zZ` (maps to HEALTH\_ERR/CRIT).

2.  **Storage Usage (`burn`):**

      * Standard Ceph "usage" is mapped to "burn".
      * Standard "used" is mapped to "burnt".
      * Standard "avail" is mapped to "loose".
      * *Logic:* Extract the numeric value and unit before `burnt` and calculate percentage against the total (burnt + loose).

3.  **Throughput (`hustle`):**

      * Standard "client" io is mapped to "hustle".
      * Standard "rd" is mapped to "in".
      * Standard "wr" is mapped to "out".
      * *Logic:* Parse `{number} {unit}/s in` and `{number} {unit}/s out` to drive the graph.

4.  **Placement Groups (`chunkz`):**

      * `chunkz` are "pgs".
      * `aight+allg00dYo` = `active+clean` (Perfect).
      * Any other state (e.g., `sidewonq+limpin`, `refill_holdUP`) implies activity or degradation.

# VISUALIZATION STRATEGY (64x64 Grid)

Create a GUI dashboard on the 64x64 grid:

  * **Top Bar (Row 0-8):** Cluster Vibe.
      * Fill Green if `AWW_YEAH`.
      * Flash Orange if `OH_ShNAPP`.
      * Flash Red (strobe) if `OH_n000zZ`.
  * **Center (Row 12-40):** Storage Burn.
      * Draw a horizontal progress bar based on the parsed "burnt" vs "loose" calculation.
      * Color gradient: Green -\> Yellow -\> Red as it fills up.
  * **Bottom (Row 45-63):** Hustle Graph.
      * A scrolling line graph (update every 5s).
      * Use Cyan for "in" (read) and Magenta for "out" (write).
  * **Overlay:** If `muscle` (OSDs) count is down (parse "X up, Y in" - if X \!= Y), draw a small warning pixel/icon in the top right corner.

# TECHNICAL CONSTRAINTS

1.  **Language:** Python 3.
2.  **Libraries:** `requests` (for Pixoo API), `subprocess` (to run cstat), `re`, `time`.
3.  **Pixoo Connection:** IP address from env var `PIXOO_IP`. Push images via HTTP POST (JSON `{"PicID": ..., "PicData": ...}` or similar depending on Pixoo API docs you find).
4.  **Loop:** Run `cstat` every 5 seconds.

# STRATEGY FOR THE AI

  - **Start by creating a high-level file structure.** Define the main loop, function signatures, and mock input data (using the sample above) to ensure parsing works before touching hardware.
  - **In the next iteration, implement the core logic.** Write the Regex engine to map `OH_ShNAPP` -\> Warn, calculate storage %, and parse bandwidth integers.
  - **In the subsequent iteration, implement the visualization.** Write the code to convert these metrics into a 64x64 RGB array and handle the Pixoo HTTP Protocol.
  - **In the final iterations, add error handling and comments.** Ensure the script doesn't crash if `cstat` returns garbage or the Pixoo disconnects.
  - **Do not try to do everything in the first loop; break it down.**

<!-- end list -->

```
```
