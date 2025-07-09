// File: pages/api/auth/[...nextauth].ts

import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";

const allowedDomain = "westwood5.com"; // <-- CHANGE THIS TO YOUR WORKSPACE DOMAIN

export default NextAuth({
  providers: [
    GoogleProvider({
      clientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!,
      clientSecret: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_SECRET!,
      // The hd param only *suggests* the domain to Google's UI.
      authorization: { params: { hd: allowedDomain } },
    }),
  ],
  callbacks: {
    async signIn({ profile }) {
      // Extra defense: only allow users from allowedDomain.
      if (!profile?.hd || profile.hd !== allowedDomain) {
        // Log for auditing/debug
        console.warn(
          `[NextAuth] Blocked login: user not in allowed domain. Got hd=${profile?.hd}, expected ${allowedDomain}`
        );
        return false;
      }
      // Uncomment for strict allowlist (for admin/dev):
      // const allowedEmails = ["user@yourfamily.com"];
      // if (!allowedEmails.includes(profile.email)) return false;
      return true;
    },
    async session({ session, token }) {
      // Only expose what you actually need on session.user
      if (session.user) {
        session.user.email = token.email;
        session.user.hd = token.hd as string | null | undefined;
        session.user.name = token.name;
        session.user.picture = token.picture;
      }
      // Only expose the accessToken if you use Google APIs from the frontend
      // session.accessToken = token.accessToken;
      return session;
    },
    async jwt({ token, account, profile }) {
      // Persist profile fields to the token
      if (profile) {
        token.email = profile.email;
        token.hd = profile.hd;
        token.name = profile.name;
        token.picture = profile.picture;
      }
      // Pass the Google access token if you need it for further Google API calls
      if (account) {
        token.accessToken = account.access_token;
      }
      return token;
    },
  },
  // Optional: you can add custom sign-in or error pages here
  // pages: {
  //   signIn: "/auth/signin",
  //   error: "/auth/error"
  // },
  // Enable debug mode in development for more logs
  // debug: process.env.NODE_ENV !== "production"
});
