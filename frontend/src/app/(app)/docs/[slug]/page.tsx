"use client";

import { useParams } from "next/navigation";

import { DocsLayout } from "@/components/docs";

export default function DocsArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  return <DocsLayout slug={slug} />;
}
