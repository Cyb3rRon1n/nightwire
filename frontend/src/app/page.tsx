import { redirect } from "next/navigation";

// The game lives at /nightwire; the root just sends players there.
export default function Home() {
  redirect("/nightwire");
}
