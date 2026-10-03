--[[
  AutoPlaylist - VLC 3.x Lua extension
  MIT License - Copyright (c) 2026 Keenan

  Scans a folder, detects media files by extension, and builds the playlist.
  Optional THEME toggles (Comedy, Horror, ...) filter and arrange the playlist.

  Install: copy into the VLC extensions folder, then Tools > Plugins and
  Extensions > Active Extensions > Reload extensions (or restart VLC).
    Windows: C:\Program Files\VideoLAN\VLC\lua\extensions\
             or %APPDATA%\vlc\lua\extensions\
    macOS:   /Applications/VLC.app/Contents/MacOS/share/lua/extensions/
    Linux:   ~/.local/share/vlc/lua/extensions/

  Run: View > AutoPlaylist (Windows/Linux), VLC > Extensions (macOS)

  How themes are detected (a video matches a theme if any source hits):
    1. Whole-word keywords in the file name and folder names
       (the scanned folder's own name counts, so scanning ...\Horror works).
       Multi-word titles also match when every significant word appears,
       in any order: "Hangover Part II" matches the hangover, "Office Space"
       matches the office. Near-misses with too little to go on
       ("Stand by Me" vs the keyword "stand up") still do not match.
    2. <genre>, <director>, <actor> and <title> tags in Kodi/Jellyfin-style
       .nfo files next to the video (MediaTidy writes these):
       <name>.nfo, movie.nfo, tvshow.nfo (same folder or the parent folder).
    3. Your own keywords/titles in auto_playlist_themes.txt (use the
       "Export themes file" button to create it in VLC's user data folder).

  Folder drop-down: recently scanned folders (most recent first, up to 10)
  followed by your Music / Videos / Movies / Downloads folders if they exist.
  Typing a path in the text box overrides the drop-down and is added to it.

  Notes on VLC's Lua sandbox:
  - No package/os/io libraries and no string methods (s:lower() fails), so
    this file uses string.lower(s) style only.
  - descriptor() is read in a bare state with no std libs, so top-level code
    must not call string/table/math.
]]

local MAX_DEPTH = 12
local MAX_RECENT = 10
local COLS = 4          -- theme check boxes per row

local AUDIO, VIDEO
local recents = {}      -- saved folders, most recent first
local folder_list = {}  -- what the drop-down shows; drop-down id = index here
local themes = {}       -- { name = "Comedy", kw = { " keyword ", ... } }
local theme_cbs = {}
local nfo_cache = {}

local dlg, in_folder, dd_folder, cb_recursive, cb_clear, cb_play, cb_m3u, cb_nfo
local dd_filter, dd_sort, dd_match, lbl_status

function descriptor()
  return {
    title = "AutoPlaylist",
    version = "1.6",
    author = "",
    shortdesc = "AutoPlaylist",
    description = "Scans a folder, detects audio/video files, and builds themed playlists automatically.",
    capabilities = {}
  }
end

---------------------------------------------------------------- built-in themes
-- Starter keywords: genre words plus distinctive titles. Add your own titles
-- in auto_playlist_themes.txt. Matching is whole-word, case-insensitive.
local function builtin_themes()
  return {
    { "Comedy", "comedy, comedies, sitcom, stand up, standup, sketch show, parody, spoof, airplane, superbad, anchorman, step brothers, bridesmaids, the hangover, dumb and dumber, ghostbusters, monty python, the office, seinfeld, parks and recreation, arrested development, brooklyn nine nine, hot fuzz, shaun of the dead, the big lebowski, groundhog day, caddyshack, office space, wedding crashers, old school, napoleon dynamite, zoolander, dodgeball, elf, mean girls, clueless, coming to america, trading places, ferris bueller, this is spinal tap, borat, knocked up" },
    { "Horror", "horror, slasher, zombie, zombies, haunted, creepy, scream, halloween, friday the 13th, nightmare on elm street, texas chainsaw massacre, the exorcist, hereditary, midsommar, the conjuring, insidious, sinister, paranormal activity, evil dead, the shining, nosferatu, poltergeist, the ring, the grudge, a quiet place" },
    { "Action", "action, martial arts, heist, die hard, john wick, mad max, mission impossible, the matrix, terminator, lethal weapon, fast and furious, rambo, predator, bourne, the expendables, kill bill, top gun, gladiator, raiders of the lost ark, indiana jones" },
    { "Sci-Fi", "sci fi, scifi, science fiction, space opera, cyberpunk, star wars, star trek, blade runner, interstellar, the matrix, alien, aliens, dune, gattaca, back to the future, 2001 a space odyssey, the martian, ex machina, district 9, black mirror, doctor who, the expanse, battlestar galactica" },
    { "Fantasy", "fantasy, sword and sorcery, wizard, wizards, dragons, lord of the rings, the hobbit, harry potter, game of thrones, narnia, the princess bride, stardust, the witcher, house of the dragon, pan s labyrinth, pans labyrinth" },
    { "Thriller", "thriller, suspense, psychological thriller, the silence of the lambs, gone girl, shutter island, zodiac, memento, the usual suspects, cape fear, the sixth sense, se7en, no country for old men, nightcrawler, rear window, vertigo, north by northwest" },
    { "Drama", "drama, shawshank redemption, forrest gump, the godfather, schindler s list, schindlers list, 12 angry men, good will hunting, whiplash, the green mile, american beauty, a beautiful mind, moonlight, oppenheimer" },
    { "Romance", "romance, romantic, rom com, romcom, titanic, the notebook, pride and prejudice, casablanca, when harry met sally, pretty woman, dirty dancing, love actually, sleepless in seattle, la la land, 10 things i hate about you, notting hill, before sunrise" },
    { "Crime", "crime, gangster, mafia, film noir, detective, goodfellas, scarface, pulp fiction, reservoir dogs, the departed, breaking bad, the sopranos, the wire, fargo, chinatown, l a confidential" },
    { "Animation", "animation, animated, cartoon, cartoons, anime, toy story, finding nemo, shrek, spirited away, the lion king, south park, the simpsons, family guy, futurama, rick and morty, adventure time, akira, my neighbor totoro, princess mononoke, spider verse, coco, moana" },
    { "Documentary", "documentary, documentaries, docuseries, true crime, planet earth, blue planet, cosmos, making a murderer, the last dance, free solo, man on wire, the act of killing, the social dilemma, my octopus teacher, icarus, march of the penguins, super size me, bowling for columbine" },
    { "Family", "family movie, family film, family night, kids movie, disney, pixar, home alone, the goonies, matilda, paddington, mrs doubtfire, jumanji, the muppets, wallace and gromit, the sandlot, the parent trap, honey i shrunk the kids, a christmas story" },
  }
end

---------------------------------------------------------------- helpers
local function words(s)
  local t = {}
  for w in string.gmatch(s, "%S+") do t[w] = true end
  return t
end

-- Forward declaration: filled in init_tables(), which runs after
-- activation. (VLC runs top-level extension code without the string
-- library, so words() can't execute at top level.)
local STOPW

local function init_tables()
  if AUDIO then return end
  AUDIO = words("mp3 flac wav ogg oga opus m4a aac wma aiff aif ape wv mka mpc")
  VIDEO = words("mp4 mkv avi mov wmv flv webm m4v mpg mpeg ts m2ts vob ogv 3gp divx")
  STOPW = words("the and of a an in on at to for vs with de la le du der die das s d l i")
end

local function sep_of(path)
  if string.find(path, "\\", 1, true) then return "\\" end
  return "/"
end

local function trim(s)
  s = string.gsub(s, "^%s+", "")
  s = string.gsub(s, "%s+$", "")
  return s
end

local function clean_path(s)
  s = trim(s)
  s = string.gsub(s, '^"(.*)"$', "%1")
  s = string.gsub(s, "[/\\]+$", "")
  return s
end

-- lower-case, every run of non-alphanumerics becomes one space
local function norm(s)
  local n = string.gsub(string.lower(s), "[^%w]+", " ")
  return trim(n)
end

local function dir_of(path)
  return string.match(path, "^(.*)[/\\][^/\\]*$")
end

local function can_scan()
  return vlc.io ~= nil and vlc.io.readdir ~= nil
end

local function userdata_file(name)
  local base = vlc.config.userdatadir()
  return base .. sep_of(base) .. name
end

local function read_all(path)
  if not (vlc.io and vlc.io.open) then return nil end
  local ok, f = pcall(vlc.io.open, path, "r")
  if not ok or not f then return nil end
  local ok2, data = pcall(function() return f:read("*a") end)
  pcall(function() f:close() end)
  if ok2 then return data end
  return nil
end

---------------------------------------------------------------- saved folders
-- file format: one folder per line, most recent first
local function read_recents()
  local t = {}
  local data = read_all(userdata_file("auto_playlist.cfg"))
  if data then
    for line in string.gmatch(data, "[^\r\n]+") do
      if #t < MAX_RECENT then t[#t + 1] = line end
    end
  end
  return t
end

local function save_recents()
  if not (vlc.io and vlc.io.open) then return end
  local ok, f = pcall(vlc.io.open, userdata_file("auto_playlist.cfg"), "w")
  if not ok or not f then return end
  pcall(function() f:write(table.concat(recents, "\n") .. "\n"); f:close() end)
end

local function add_recent(path)
  local t = { path }
  for _, p in ipairs(recents) do
    if p ~= path and #t < MAX_RECENT then t[#t + 1] = p end
  end
  recents = t
  save_recents()
end

local function default_folders()
  local out = {}
  if not can_scan() then return out end
  local ok, home = pcall(function() return vlc.config.homedir() end)
  if not ok or not home or home == "" then return out end
  home = string.gsub(home, "[/\\]+$", "")
  local s = sep_of(home)
  for _, name in ipairs({ "Music", "Videos", "Movies", "Downloads" }) do
    local p = home .. s .. name
    local ok2, entries = pcall(vlc.io.readdir, p)
    if ok2 and entries then out[#out + 1] = p end
  end
  return out
end

local function refill_dropdown(initial)
  if not initial then
    -- if this VLC build can't clear a drop-down, leave it as is
    local ok = pcall(function() dd_folder:clear() end)
    if not ok then return end
  end
  folder_list = {}
  local seen = {}
  for _, p in ipairs(recents) do
    if not seen[p] then seen[p] = true; folder_list[#folder_list + 1] = p end
  end
  for _, p in ipairs(default_folders()) do
    if not seen[p] then seen[p] = true; folder_list[#folder_list + 1] = p end
  end
  if #folder_list == 0 then
    dd_folder:add_value("(no saved folders - type a path below)", 0)
  else
    for i, p in ipairs(folder_list) do dd_folder:add_value(p, i) end
  end
end

local function remember(dir)
  add_recent(dir)
  refill_dropdown(false)
  in_folder:set_text("")
  dlg:update()
end

---------------------------------------------------------------- themes
local function split_commas(s)
  local out = {}
  for part in string.gmatch(s, "[^,]+") do
    local n = norm(part)
    if n ~= "" then out[#out + 1] = n end
  end
  return out
end

-- words too small or too common to identify a title on their own
-- (STOPW is declared near the top and filled in init_tables())

-- significant words of a keyword phrase, for order-free matching
local function core_words(phrase)
  local out, seen = {}, {}
  for w in string.gmatch(phrase, "%w+") do
    if string.len(w) >= 4 and not STOPW[w] and not seen[w] then
      seen[w] = true
      out[#out + 1] = w
    end
  end
  return out
end

-- built-ins first, then lines from auto_playlist_themes.txt:
--   Name: keyword, keyword, ...     (adds to a same-named theme, or creates one)
local function load_themes()
  themes = {}
  local byname = {}
  local function add(name, kwtext)
    local key = string.lower(name)
    local th = byname[key]
    if not th then
      th = { name = name, kw = {} }
      byname[key] = th
      themes[#themes + 1] = th
    end
    for _, kw in ipairs(split_commas(kwtext)) do
      th.kw[#th.kw + 1] = { ph = " " .. kw .. " ", core = core_words(kw) }
    end
  end
  for _, t in ipairs(builtin_themes()) do add(t[1], t[2]) end

  local data = read_all(userdata_file("auto_playlist_themes.txt"))
  if data then
    for line in string.gmatch(data, "[^\r\n]+") do
      if string.sub(trim(line), 1, 1) ~= "#" then
        local name, kws = string.match(line, "^%s*([^:]-)%s*:%s*(.*)$")
        if name and name ~= "" and kws and kws ~= "" then add(name, kws) end
      end
    end
  end
end

local function theme_matches(th, hay)
  for _, k in ipairs(th.kw) do
    if string.find(hay, k.ph, 1, true) then return true end
    -- order-free fallback: every significant word present as a whole word.
    -- A lone significant word only counts when long enough to be distinctive
    -- ("hangover", "office"), so "Stand by Me" never matches "stand up".
    local n = #k.core
    if n >= 2 then
      local all = true
      for _, w in ipairs(k.core) do
        if not string.find(hay, " " .. w .. " ", 1, true) then all = false; break end
      end
      if all then return true end
    elseif n == 1 and string.len(k.core[1]) >= 6 then
      if string.find(hay, " " .. k.core[1] .. " ", 1, true) then return true end
    end
  end
  return false
end

local function export_themes_inner()
  local path = userdata_file("auto_playlist_themes.txt")
  if read_all(path) then
    lbl_status:set_text("Themes file already exists: " .. path)
    return
  end
  if not (vlc.io and vlc.io.open) then
    lbl_status:set_text("This VLC build can't write files.")
    return
  end
  local ok, f = pcall(vlc.io.open, path, "w")
  if not ok or not f then
    lbl_status:set_text("Could not write " .. path)
    return
  end
  local lines = {
    "# AutoPlaylist - custom themes",
    "# One theme per line:   Theme name: keyword, keyword, another keyword",
    "# Keywords match whole words in file names, folder names and .nfo tags (title/genre/director/actors, case-insensitive).",
    "# Multi-word titles also match when all their significant words appear, in any order.",
    "# A line ADDS keywords to a built-in theme with the same name, or creates a new theme.",
    "# Add movie/show titles here to teach the tool what they are.",
    "# Close and reopen the extension after editing.",
    "#",
    "# Examples (remove the leading # to use):",
    "# Horror: my scary movie title, another title",
    "# Date Night: romance, comedy, some title",
    "#",
    "# Built-in keywords, for reference (already active):",
  }
  for _, t in ipairs(builtin_themes()) do
    lines[#lines + 1] = "# " .. t[1] .. ": " .. t[2]
  end
  local wrote = pcall(function() f:write(table.concat(lines, "\n") .. "\n"); f:close() end)
  if wrote then
    lbl_status:set_text("Saved " .. path .. " - edit it, then reopen the extension.")
  else
    lbl_status:set_text("Could not write " .. path)
  end
end

local function export_themes()
  local ok, err = pcall(export_themes_inner)
  if not ok and lbl_status then lbl_status:set_text("Error: " .. tostring(err)) end
end

---------------------------------------------------------------- .nfo tags
-- MediaTidy writes Kodi-style .nfo files with <genre>, <director>,
-- <actor><name> and <title> tags. All of them feed theme matching, so
-- e.g. a "Tarantino" keyword or a custom theme matches the director.
local function nfo_text_at(path)
  local c = nfo_cache[path]
  if c ~= nil then return c end
  local result = false
  local data = read_all(path)
  if data then
    local parts = {}
    for g in string.gmatch(data, "<genre>%s*(.-)%s*</genre>") do
      parts[#parts + 1] = g
    end
    for d in string.gmatch(data, "<director>%s*(.-)%s*</director>") do
      parts[#parts + 1] = d
    end
    for a in string.gmatch(data, "<actor>%s*<name>%s*(.-)%s*</name>") do
      parts[#parts + 1] = a
    end
    for t in string.gmatch(data, "<title>%s*(.-)%s*</title>") do
      parts[#parts + 1] = t
    end
    if #parts > 0 then result = norm(table.concat(parts, " ")) end
  end
  nfo_cache[path] = result
  return result
end

local function item_nfo_text(it)
  local d = dir_of(it.path)
  if not d then return nil end
  local s = sep_of(d)
  local base = string.gsub(it.path, "%.[^%./\\]+$", "")
  local cands = { base .. ".nfo", d .. s .. "movie.nfo", d .. s .. "tvshow.nfo" }
  local parent = dir_of(d)
  if parent then cands[#cands + 1] = parent .. s .. "tvshow.nfo" end
  local found = {}
  for _, p in ipairs(cands) do
    local g = nfo_text_at(p)
    if g then found[#found + 1] = g end
  end
  if #found == 0 then return nil end
  return table.concat(found, " ")
end

---------------------------------------------------------------- scanning
local function scan(dir, ctx, depth)
  local ok, entries = pcall(vlc.io.readdir, dir)
  if not ok or not entries then return end
  for _, name in ipairs(entries) do
    if string.sub(name, 1, 1) ~= "." then
      local full = dir .. sep_of(dir) .. name
      local ext = string.match(name, "%.([^%.]+)$")
      if ext then ext = string.lower(ext) end
      if ext and (AUDIO[ext] or VIDEO[ext]) then
        ctx.out[#ctx.out + 1] = {
          path = full,
          name = name,
          kind = AUDIO[ext] and "audio" or "video",
          rel = ctx.rootname .. "/" .. string.sub(full, ctx.rootlen + 2),
        }
      elseif ctx.recursive and depth < MAX_DEPTH then
        scan(full, ctx, depth + 1)
      end
    end
  end
end

-- tag each item with the selected themes it matches
local function classify(items, selected, use_nfo)
  local nfo_n = 0
  for _, it in ipairs(items) do
    local hay = " " .. norm(it.rel) .. " "
    if use_nfo and it.kind == "video" then
      local g = item_nfo_text(it)
      if g then hay = hay .. g .. " "; nfo_n = nfo_n + 1 end
    end
    it.match, it.hits, it.theme = {}, 0, nil
    for _, ti in ipairs(selected) do
      if theme_matches(themes[ti], hay) then
        it.match[ti] = true
        it.hits = it.hits + 1
        if not it.theme then it.theme = ti end -- primary theme = first selected match
      end
    end
  end
  return nfo_n
end

local function filter_by_themes(items, selected, need_all)
  local kept = {}
  for _, it in ipairs(items) do
    if (need_all and it.hits == #selected) or (not need_all and it.hits >= 1) then
      kept[#kept + 1] = it
    end
  end
  return kept
end

---------------------------------------------------------------- ordering
local function natural_key(s)
  local k = string.gsub(string.lower(s), "%d+", function(n)
    if #n < 10 then return string.rep("0", 10 - #n) .. n end
    return n
  end)
  return k
end

local function by_key(a, b) return a.key < b.key end

local function sort_items(items, mode, selected)
  for _, it in ipairs(items) do it.key = natural_key(it.path) end

  if mode == 3 then -- shuffle
    math.randomseed(vlc.misc.mdate() % 2147483647)
    for i = #items, 2, -1 do
      local j = math.random(i)
      items[i], items[j] = items[j], items[i]
    end
  elseif mode == 2 then -- type, then name
    table.sort(items, function(a, b)
      if a.kind ~= b.kind then return a.kind < b.kind end
      return a.key < b.key
    end)
  elseif (mode == 4 or mode == 5) and #selected > 0 then
    -- 4 = group by theme, 5 = mix themes (alternate between themes)
    table.sort(items, function(a, b)
      if a.theme ~= b.theme then return a.theme < b.theme end
      return a.key < b.key
    end)
    if mode == 5 then
      local buckets, order = {}, {}
      for _, it in ipairs(items) do
        if not buckets[it.theme] then buckets[it.theme] = {}; order[#order + 1] = it.theme end
        local b = buckets[it.theme]
        b[#b + 1] = it
      end
      local mixed, i, left = {}, 1, #items
      while left > 0 do
        for _, th in ipairs(order) do
          local it = buckets[th][i]
          if it then mixed[#mixed + 1] = it; left = left - 1 end
        end
        i = i + 1
      end
      for k = 1, #mixed do items[k] = mixed[k] end
    end
  else -- name (natural)
    table.sort(items, by_key)
  end
end

local function write_m3u(dir, items)
  if not (vlc.io and vlc.io.open) then return false end
  local ok, f = pcall(vlc.io.open, dir .. sep_of(dir) .. "auto_playlist.m3u", "w")
  if not ok or not f then return false end
  local wrote = pcall(function()
    f:write("#EXTM3U\n")
    for _, it in ipairs(items) do
      f:write("#EXTINF:-1," .. it.name .. "\n" .. it.path .. "\n")
    end
    f:close()
  end)
  return wrote
end

---------------------------------------------------------------- actions
local function build_inner()
  init_tables()
  nfo_cache = {}

  -- typed path wins; otherwise use the drop-down selection
  local dir = clean_path(in_folder:get_text())
  if dir == "" then dir = folder_list[dd_folder:get_value()] or "" end
  if dir == "" then
    lbl_status:set_text("Pick a folder or type a path.")
    return
  end

  local selected, names = {}, {}
  for i = 1, #themes do
    if theme_cbs[i] and theme_cbs[i]:get_checked() then
      selected[#selected + 1] = i
      names[#names + 1] = themes[i].name
    end
  end

  local items = {}
  local scanning = can_scan()
  if scanning then
    local rootname = string.match(dir, "([^/\\]+)$") or dir
    scan(dir, { out = items, recursive = cb_recursive:get_checked(),
                rootname = rootname, rootlen = #dir }, 0)
  elseif #selected > 0 then
    lbl_status:set_text("Themes need folder scanning, which this VLC build lacks.")
    return
  end

  local filter = dd_filter:get_value() -- 1 audio+video, 2 audio, 3 video
  if filter ~= 1 then
    local want = (filter == 2) and "audio" or "video"
    local kept = {}
    for _, it in ipairs(items) do
      if it.kind == want then kept[#kept + 1] = it end
    end
    items = kept
  end

  local n_scanned, nfo_n = #items, 0
  if scanning and #selected > 0 and n_scanned > 0 then
    nfo_n = classify(items, selected, cb_nfo:get_checked())
    items = filter_by_themes(items, selected, dd_match:get_value() == 2)
  end

  if scanning and #items == 0 then
    if #selected > 0 and n_scanned > 0 then
      lbl_status:set_text("0 of " .. n_scanned .. " files match: " .. table.concat(names, ", "))
    else
      lbl_status:set_text("0 media files found in " .. dir)
    end
    return
  end

  if cb_clear:get_checked() then vlc.playlist.clear() end

  if not scanning then
    -- fallback: let VLC expand the directory itself
    vlc.playlist.enqueue({ { path = vlc.strings.make_uri(dir), name = dir } })
    remember(dir)
    lbl_status:set_text("Folder added (folder scan unavailable, VLC expanded it).")
    if cb_play:get_checked() then vlc.playlist.play() end
    return
  end

  sort_items(items, dd_sort:get_value(), selected)

  local tracks, n_audio, n_video = {}, 0, 0
  for _, it in ipairs(items) do
    tracks[#tracks + 1] = { path = vlc.strings.make_uri(it.path), name = it.name }
    if it.kind == "audio" then n_audio = n_audio + 1 else n_video = n_video + 1 end
  end
  vlc.playlist.enqueue(tracks)
  remember(dir)

  local m3u = ""
  if cb_m3u:get_checked() then
    if write_m3u(dir, items) then m3u = " | m3u saved" else m3u = " | m3u write failed" end
  end

  local theme_info = ""
  if #selected > 0 then
    local parts = {}
    for _, ti in ipairs(selected) do
      local c = 0
      for _, it in ipairs(items) do
        if it.match[ti] then c = c + 1 end
      end
      parts[#parts + 1] = themes[ti].name .. " " .. c
    end
    theme_info = " | " .. table.concat(parts, ", ")
    if nfo_n > 0 then theme_info = theme_info .. " | .nfo: " .. nfo_n end
  end

  lbl_status:set_text(string.format("%d files (%d audio, %d video)%s%s",
    #items, n_audio, n_video, theme_info, m3u))

  if cb_play:get_checked() then vlc.playlist.play() end
end

local function build()
  local ok, err = pcall(build_inner)
  if not ok and lbl_status then
    lbl_status:set_text("Error: " .. tostring(err))
  end
end

function close() vlc.deactivate() end

---------------------------------------------------------------- lifecycle
local function activate_inner()
  init_tables()
  recents = read_recents()
  load_themes()
  theme_cbs = {}
  nfo_cache = {}

  dlg = vlc.dialog("AutoPlaylist")

  dlg:add_label("Folder:", 1, 1, 1, 1)
  dd_folder = dlg:add_dropdown(2, 1, 3, 1)
  refill_dropdown(true)

  dlg:add_label("Or type path:", 1, 2, 1, 1)
  in_folder = dlg:add_text_input("", 2, 2, 3, 1)

  -- first value added is the default selection: video first
  dlg:add_label("Media:", 1, 3, 1, 1)
  dd_filter = dlg:add_dropdown(2, 3, 3, 1)
  dd_filter:add_value("Video only", 3)
  dd_filter:add_value("Audio + video", 1)
  dd_filter:add_value("Audio only", 2)

  dlg:add_label("Order:", 1, 4, 1, 1)
  dd_sort = dlg:add_dropdown(2, 4, 3, 1)
  dd_sort:add_value("Name (natural)", 1)
  dd_sort:add_value("Type, then name", 2)
  dd_sort:add_value("Shuffle", 3)
  dd_sort:add_value("Group by theme", 4)
  dd_sort:add_value("Mix themes (alternate)", 5)

  local r = 5
  dlg:add_label("Themes (toggle any; none selected = no filter):", 1, r, COLS, 1)
  r = r + 1
  for i, th in ipairs(themes) do
    local col = ((i - 1) % COLS) + 1
    local row = r + math.floor((i - 1) / COLS)
    theme_cbs[i] = dlg:add_check_box(th.name, false, col, row, 1, 1)
  end
  r = r + math.floor((#themes - 1) / COLS) + 1

  dlg:add_label("Match:", 1, r, 1, 1)
  dd_match = dlg:add_dropdown(2, r, 1, 1)
  dd_match:add_value("Any selected theme", 1)
  dd_match:add_value("All selected themes", 2)
  cb_nfo = dlg:add_check_box("Read .nfo tags (genre/director/actors)", true, 3, r, 2, 1)
  r = r + 1

  cb_recursive = dlg:add_check_box("Include subfolders", true, 1, r, 2, 1)
  cb_clear     = dlg:add_check_box("Clear playlist first", true, 3, r, 2, 1)
  r = r + 1
  cb_play      = dlg:add_check_box("Start playing", true, 1, r, 2, 1)
  cb_m3u       = dlg:add_check_box("Save auto_playlist.m3u in folder", false, 3, r, 2, 1)
  r = r + 1

  dlg:add_button("Scan && Build", build, 1, r, 2, 1)
  dlg:add_button("Export themes file", export_themes, 3, r, 1, 1)
  dlg:add_button("Close", close, 4, r, 1, 1)
  r = r + 1
  lbl_status = dlg:add_label("", 1, r, COLS, 1)
  dlg:show()
end

function activate()
  local ok, err = pcall(activate_inner)
  if not ok then vlc.msg.err("AutoPlaylist: " .. tostring(err)) end
end

function deactivate()
  if dlg then dlg:delete(); dlg = nil end
end
