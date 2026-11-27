"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// In the demo you're already signed in as the sample company's owner.
export default function DemoStart() {
  const router = useRouter();
  useEffect(() => router.replace("/dashboard"), [router]);
  return null;
}
