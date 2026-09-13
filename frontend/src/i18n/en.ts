export const en = {
  shared: {
    loading: "Loading",
    pleaseWait: "Please wait…",
  },
  signIn: {
    offline: "Sign-in requires an internet connection.",
    magicLinkError: "We could not send the magic link",
    invalidCredentials: "That email or password is not correct.",
    signInError: "We could not sign you in. Please try again.",
    googleError: "Google sign-in failed",
    tagline: "Bịanụ. Your Igbo learning journey starts here.",
    welcome: "Welcome",
    heading: "Sign in to continue",
    google: "Continue with Google",
    emailDivider: "or continue with email",
    email: "Email address",
    emailPlaceholder: "you@example.com",
    password: "Password",
    signIn: "Sign in",
    useMagicLink: "Use a magic link instead",
    checkEmail: "Check your email",
    sentLink: "We sent a secure sign-in link to",
    sendMagicLink: "Send magic link",
    usePassword: "Sign in with a password instead",
  },
  home: {
    continueCta: "Continue",
  },
  onboarding: {
    heritageSpeaker: "Igbo heritage speaker",
  },
} as const;

export type UiStrings = typeof en;
