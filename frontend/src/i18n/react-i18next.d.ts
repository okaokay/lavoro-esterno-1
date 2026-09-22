/** Collega le risorse italiane ai tipi di i18next per validare le chiavi. */
import "i18next";
import type { TranslationResources } from "./it";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: TranslationResources;
  }
}
