/**
 * PublicChatBubble — mounts the floating NxtChatBot on public marketing routes.
 *
 * Visible on: /, /access, /signup, /signin, /privacy, /terms
 * Hidden on:  /contact (inline chat already there), and ALL authenticated
 *             /workspace, /builder, /agentos, /preview routes.
 */
import { useLocation } from "react-router-dom";
import NxtChatBot from "@/components/landing/NxtChatBot";

const PUBLIC_ROUTES = ["/", "/access", "/signup", "/signin", "/privacy", "/terms"];

export default function PublicChatBubble() {
  const { pathname } = useLocation();
  if (!PUBLIC_ROUTES.includes(pathname)) return null;
  return <NxtChatBot floating />;
}
