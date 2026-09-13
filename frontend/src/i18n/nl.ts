import type { UiStrings } from "./en";

export type DeepPartial<T> = {
  [Key in keyof T]?: T[Key] extends string ? string : DeepPartial<T[Key]>;
};

export const nl = {
  shared: {
    loading: "Laden",
    pleaseWait: "Even geduld…",
  },
  signIn: {
    offline: "Je hebt internet nodig om in te loggen.",
    magicLinkError: "We konden de inloglink niet versturen",
    invalidCredentials: "Dat e-mailadres of wachtwoord klopt niet.",
    signInError: "Inloggen is niet gelukt. Probeer het nog eens.",
    googleError: "Inloggen met Google is niet gelukt",
    tagline: "Bịanụ. Hier begint je reis om Igbo te leren.",
    welcome: "Welkom",
    heading: "Log in om verder te gaan",
    google: "Doorgaan met Google",
    emailDivider: "of ga verder met e-mail",
    email: "E-mailadres",
    emailPlaceholder: "jij@voorbeeld.nl",
    password: "Wachtwoord",
    signIn: "Inloggen",
    useMagicLink: "Gebruik liever een inloglink",
    checkEmail: "Kijk in je e-mail",
    sentLink: "We hebben een veilige inloglink gestuurd naar",
    sendMagicLink: "Inloglink sturen",
    usePassword: "Log liever in met een wachtwoord",
  },
  home: {
    continueCta: "Doorgaan",
  },
  onboarding: {},
} satisfies DeepPartial<UiStrings>;
