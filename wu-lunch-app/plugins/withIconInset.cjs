const {withDangerousMod} = require('expo/config-plugins');
const fs = require('node:fs/promises');
const path = require('node:path');

module.exports = config => withDangerousMod(config, ['android', async mod => {
  const res = path.join(mod.modRequest.platformProjectRoot, 'app/src/main/res');
  await fs.mkdir(path.join(res, 'drawable'), {recursive: true});
  await fs.writeFile(path.join(res, 'drawable/ic_launcher_foreground_inset.xml'), '<?xml version="1.0" encoding="utf-8"?><inset xmlns:android="http://schemas.android.com/apk/res/android" android:drawable="@mipmap/ic_launcher_foreground" android:inset="20%" />');
  for (const directory of await fs.readdir(res)) {
    if (!directory.startsWith('mipmap-anydpi')) continue;
    for (const file of await fs.readdir(path.join(res, directory))) {
      if (!/^ic_launcher.*\.xml$/.test(file)) continue;
      const target = path.join(res, directory, file);
      const xml = await fs.readFile(target, 'utf8');
      await fs.writeFile(target, xml.replace(/@mipmap\/ic_launcher_foreground/g, '@drawable/ic_launcher_foreground_inset'));
    }
  }
  return mod;
}]);
