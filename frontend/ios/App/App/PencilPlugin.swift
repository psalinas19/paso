import Capacitor
import UIKit

/// The one thing the web version cannot have: the Apple Pencil double tap.
///
/// Safari never tells a web page about it, so this small plugin listens natively
/// and forwards it to the notebook as a "doubleTap" event. What the tap *does*
/// is decided on the web side (frontend/src/native/pencil.ts), so the gesture
/// behaves like the rest of the toolbar.
@objc(PencilPlugin)
public class PencilPlugin: CAPPlugin, CAPBridgedPlugin, UIPencilInteractionDelegate {
    public let identifier = "PencilPlugin"
    public let jsName = "Pencil"
    // No callable methods: the plugin only emits events.
    public let pluginMethods: [CAPPluginMethod] = []

    private var lastTap: TimeInterval = 0

    @objc override public func load() {
        DispatchQueue.main.async {
            let interaction = UIPencilInteraction()
            interaction.delegate = self
            self.bridge?.webView?.addInteraction(interaction)
        }
    }

    // iPadOS 17.5 and later.
    @available(iOS 17.5, *)
    public func pencilInteraction(_ interaction: UIPencilInteraction, didReceiveTap tap: UIPencilInteraction.Tap) {
        report()
    }

    // Before iPadOS 17.5.
    public func pencilInteractionDidTap(_ interaction: UIPencilInteraction) {
        report()
    }

    private func report() {
        // Settings > Apple Pencil > "Off" means the user wants no double tap anywhere.
        guard UIPencilInteraction.preferredTapAction != .ignore else { return }
        // If a system version ever calls both delegate methods, count it once.
        let now = ProcessInfo.processInfo.systemUptime
        guard now - lastTap > 0.15 else { return }
        lastTap = now
        notifyListeners("doubleTap", data: [:])
    }
}

/// The app's only screen: Capacitor's web view, plus our plugin.
class PasoViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(PencilPlugin())
    }
}
