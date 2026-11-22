// Die App läuft nur im Hochformat. Android leitet daraus ab, dass ein Gerät Hochformat „haben muss"
// (android.hardware.screen.portrait), und Google Play warnt, das schränke die Verfügbarkeit ein.
// Diese Angabe kennzeichnet die Funktion als nicht erforderlich; am Verhalten der App ändert sich nichts.
const { withAndroidManifest } = require('expo/config-plugins');

const FEATURE = 'android.hardware.screen.portrait';

function addOptionalPortrait(manifest) {
  const features = (manifest['uses-feature'] || []).filter(entry => entry.$?.['android:name'] !== FEATURE);
  features.push({ $: { 'android:name': FEATURE, 'android:required': 'false' } });
  manifest['uses-feature'] = features;
  return manifest;
}

module.exports = config => withAndroidManifest(config, result => {
  addOptionalPortrait(result.modResults.manifest);
  return result;
});
module.exports.addOptionalPortrait = addOptionalPortrait;
