claude.sh -p "why does app/main.py give this error in the test run [your-program] $ complete -p git

[your-program] complete: git: no completion specification

[tester::#TZ2] ✓ Found missing completion specification after unregister

[tester::#TZ2] Typed 'git' followed by a <SPACE>

[tester::#TZ2] ✓ Prompt line matches '$ git '

[tester::#TZ2] Pressed '<TAB>' (expecting autocomplete to 'git' followed by a space)

[your-program] $ git

[tester::#TZ2] ^ Line does not match expected value.

[tester::#TZ2] Expected: '$ git '

[tester::#TZ2] Received: '$ git   '

[tester::#TZ2] Test failed



View our article on debugging test failures: https://codecrafters.io/debug"
