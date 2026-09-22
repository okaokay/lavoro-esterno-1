/** Inizializzazione i18next: italiano unico, senza escaping React duplicato. */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { it } from "./it";

void i18n.use(initReactI18next).init({
  resources: { it },
  lng: "it",
  fallbackLng: "it",
  supportedLngs: ["it"],
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
