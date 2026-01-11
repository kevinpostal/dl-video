# VHS tape file for dl-video demo
# Run: vhs demo.tape

Output demo.gif

Set FontSize 14
Set Width 1200
Set Height 800
Set Theme "Catppuccin Mocha"

Type "make run"
Enter
Sleep 1.5s

# Type a URL
Type@50ms "https://www.youtube.com/watch?v=IBRL7D0wcXM"
Sleep 500ms

# Submit to start download
Enter
Sleep 1s

# Watch the download progress and speed graph
Sleep 15s

# Click on History tab (Tab key)
Tab
Tab
Sleep 500ms

# Click on the info icon (i) for the first entry
Type "i"
Sleep 2s

# Close the info modal
Escape
Sleep 500ms

# Quit the app
Escape
Sleep 300ms
Escape
Sleep 500ms
