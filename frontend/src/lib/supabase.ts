import { createClient } from "@supabase/supabase-js";

import { getEnvironment } from "./env";

const environment = getEnvironment();

export const supabase = createClient(
  environment.supabaseUrl,
  environment.supabaseAnonKey,
);
