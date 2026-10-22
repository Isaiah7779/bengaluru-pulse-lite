// Expo config plugin: sign Android release builds with the project's own upload key when
// it is configured, otherwise keep the template's debug signing (unchanged behaviour).
//
// The key never lives in the repository. Set these Gradle properties in the user-level
// file %USERPROFILE%\.gradle\gradle.properties (or ~/.gradle/gradle.properties):
//   PULSE_UPLOAD_STORE_FILE=C:/Users/<you>/.bengaluru-pulse-keys/bengaluru-pulse-upload.jks
//   PULSE_UPLOAD_STORE_PASSWORD=...
//   PULSE_UPLOAD_KEY_ALIAS=bengaluru-pulse-upload
//   PULSE_UPLOAD_KEY_PASSWORD=...
const { withAppBuildGradle } = require("expo/config-plugins");

const MARKER = "// bengaluru-pulse: release signing";

const RELEASE_CONFIG = `
        ${MARKER}
        if (findProperty('PULSE_UPLOAD_STORE_FILE')) {
            release {
                storeFile file(findProperty('PULSE_UPLOAD_STORE_FILE'))
                storePassword findProperty('PULSE_UPLOAD_STORE_PASSWORD')
                keyAlias findProperty('PULSE_UPLOAD_KEY_ALIAS')
                keyPassword findProperty('PULSE_UPLOAD_KEY_PASSWORD')
            }
        }`;

function addReleaseSigning(gradle) {
  if (gradle.includes(MARKER)) return gradle;
  const debugBlock = /(signingConfigs\s*\{\s*debug\s*\{[^}]*\})/;
  if (!debugBlock.test(gradle)) throw new Error("withReleaseSigning: signingConfigs.debug block not found in app/build.gradle");
  gradle = gradle.replace(debugBlock, `$1${RELEASE_CONFIG}`);
  const releaseType = /(buildTypes\s*\{[\s\S]*?release\s*\{[\s\S]*?)signingConfig signingConfigs\.debug/;
  if (!releaseType.test(gradle)) throw new Error("withReleaseSigning: release buildType signingConfig not found");
  return gradle.replace(
    releaseType,
    "$1signingConfig findProperty('PULSE_UPLOAD_STORE_FILE') ? signingConfigs.release : signingConfigs.debug"
  );
}

module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (cfg) => {
    if (cfg.modResults.language !== "groovy") throw new Error("withReleaseSigning: expected a Groovy build.gradle");
    cfg.modResults.contents = addReleaseSigning(cfg.modResults.contents);
    return cfg;
  });
};
module.exports.addReleaseSigning = addReleaseSigning;
