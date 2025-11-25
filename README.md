# Paste here your any Minecraft Packs.
  
***Note:*** *This program fully reloading your mods-folder by default.*  
*Change this by clicking on \[d\\r\] button in top-right side of window.*  
- *If d-mode: pack-files in mods-folder will rewriting your own files in .minecraft/mods;*  
- *If r-mode: pack-files in mods-folder will rewriting your files with creating backups in format .minecraft/mods-1, .minecraft/mods-2, etc.*  
  
[img]
  
This program is designed for quickly changing (primarily) MODpacks in Minecraft for to make this process take a minimum of your time.  
  
All functionality:  
- auto-modpack files loading;  
- Minecraft modifical version auto-installing (push .jar-file of Forge, Quilt, Fabric or NeoForge version installer into versions/ folder);  
- deleting or renaming mods-folders for backup-function realization (save your installed modpack if you want or not);    
- auto-server IP and Name writing into your ingame server-list with linking by modpacks;  
- share your EndLinkerio.exe-file with your friends.

To use it, create a private repository on your [Github Page](https://github.com/) and paste the link to this repo into *endlinkerio.py*, *line 25*:  
```bash
GITHUB_REPO = "USERNAME/PRIVATEREPO"
```  
  
Create the token for private repositories ***WITH NO EXPIRATION DATE*** [here](https://github.com/settings/personal-access-tokens).   
Paste it directly into the *penny.txt*-file without any additions.  
```bash
githab_pat_yourprivatetoken
```
  
Compile the program by *pyinstaller* with using the following cmd-commands (skip this any command if it's already done except for *the last one*):  
```bash
pip install python python3  
pip install pyinstaller  
pyinstaller --onefile --noconsole --icon=icons/icon.ico --add-data "icons;icons" --add-data "fonts;fonts" --add-data "penny.txt;." --hidden-import=numpy.core._dtype_ctypes --hidden-import=numpy._pytesttester --hidden-import=numpy._distributor_init endlinkerio.py
```  
  
You find your [img] *EndLinkerio.exe* in dist/-folder.
You can share this file with friends. ;)

For adding a new modpack which will be seen by your friend and you, just create folder in modpacks by example:
> modpacks/YOUR_PACK_NAME (ver. 1.n.n)/  
And paste here your own pack-files like mods/.jars, resourcepacks/.zips, config/.jsons, saves/, versions/.jars, etc.

Also you can create server.txt-file in your modpack to auto-write Name and IP of your moded server (if it exists) in ingame server-lists of users.  
Use next architecture in modpacks/YOUR_PACK_NAME (ver. 1.n.n)/*server.txt*:  
> name="Minecraft Online Server"  
> ip="example.minecrft.org"  
  
After this you must push this files in repository. You can do this by this commands-chain:  
```bash
git init .
git remote add origin https://github.com/USERNAME/PRIVATEREPO  
git add .  
git commit -m "YOUR_COMMIT"  
git push origin master  
```

Have a nice game to you and your friends! ;)