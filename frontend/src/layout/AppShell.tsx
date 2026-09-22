import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

// Shell wrapping every authenticated route: fixed sidebar + sticky topbar +
// scrollable main canvas. Rendered by the /dashboard, /search, ... parent route.
export default function AppShell() {
  return (
    <div className="bg-surface text-on-surface flex min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-sidebar-width flex flex-col min-h-screen">
        <Topbar />
        <main className="flex-1 p-margin-page bg-background overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
