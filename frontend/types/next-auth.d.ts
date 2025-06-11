// /types/next-auth.d.ts
import NextAuth, { DefaultSession, DefaultUser, Profile as DefaultProfile } from "next-auth";

declare module "next-auth" {
  interface Profile extends DefaultProfile {
    hd?: string; // Add hosted domain for Google SSO
    picture?: string; // Add picture if you want it
  }
  interface Session {
    user?: {
      name?: string | null;
      email?: string | null;
      image?: string | null;
      hd?: string | null;     // Add this line
      picture?: string | null; // If you want it
    };
    accessToken?: string;
  }
  interface User extends DefaultUser {
    hd?: string | null;
    picture?: string | null;
  }
}
