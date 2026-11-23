# Record with: vhs docs/demo.tape  (run from repo root after `make install`)
Output docs/demo.gif
Set Shell "bash"
Set FontSize 14
Set Width 1400
Set Height 400
Set Padding 18
Set Theme "Dracula"
Set TypingSpeed 45ms

Hide
Type "export PS1='$ ' && rm -f out/invoices.csv && clear" Enter
Show

Type "ls samples/" Sleep 300ms Enter
Sleep 1.2s
Type ".venv/bin/invoice-automation --mock" Sleep 300ms Enter
Sleep 3s
Type "cut -d, -f2-8,10 out/invoices.csv | column -s, -t" Sleep 300ms Enter
Sleep 4s
