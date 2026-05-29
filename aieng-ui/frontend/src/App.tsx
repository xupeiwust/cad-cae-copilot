import { AppChrome } from "./app/AppChrome";
import { useWorkbenchApp } from "./app/useWorkbenchApp";

export default function App() {
  return <AppChrome app={useWorkbenchApp()} />;
}
