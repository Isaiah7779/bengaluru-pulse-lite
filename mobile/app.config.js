// Dynamic additions to app.json (Expo merges this over the static config).
//
// * Google Sign-In: the app uses the Firebase JS SDK, not the native Firebase SDK, so the
//   @react-native-google-signin plugin runs in its "without Firebase" mode. Android needs no
//   plugin options (the native module is autolinked); iOS needs the reversed iOS OAuth
//   client ID as a URL scheme, supplied via GOOGLE_IOS_URL_SCHEME when an iOS build is made.
// * Release signing: ./plugins/withReleaseSigning reads the upload keystore location and
//   passwords from Gradle properties kept outside the repository (see docs/AUTHENTICATION.md).
module.exports = ({ config }) => {
  const plugins = [...(config.plugins || [])];
  const iosUrlScheme = process.env.GOOGLE_IOS_URL_SCHEME;
  if (iosUrlScheme) plugins.push(["@react-native-google-signin/google-signin", { iosUrlScheme }]);
  plugins.push("./plugins/withReleaseSigning");
  return { ...config, plugins };
};
