setup.py bdist_wininst --target=2.5 --user-access-control=auto
setup.py bdist_wininst --target=2.6 --user-access-control=auto
setup.py bdist_wininst --target=2.7 --user-access-control=auto
setup.py sdist --format=zip
setup.py sdist --format=gztar