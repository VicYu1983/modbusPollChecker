import {
  DeleteOutlined,
  FolderOpenOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Button, Input, Space, Tooltip, Typography } from "antd";

type SiteHeaderProps = {
  siteName: string;
  onSiteNameChange: (siteName: string) => void;
  onSiteNameSave: () => void;
  onSaveConfig: () => void;
  onReadConfig: () => void;
  onClearConfig: () => void;
};

export function SiteHeader({
  siteName,
  onSiteNameChange,
  onSiteNameSave,
  onSaveConfig,
  onReadConfig,
  onClearConfig,
}: SiteHeaderProps) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <ThunderboltOutlined />
        </div>
        <div>
          <Typography.Title level={4}>MODBUS / POLL CHECKER</Typography.Title>
          <span className="eyebrow">FIELD CONNECTION CONSOLE</span>
        </div>
      </div>
      <div className="site-switcher">
        <span className="muted-label">目前案場</span>
        <Input
          value={siteName}
          onChange={(event) => onSiteNameChange(event.target.value)}
          onBlur={onSiteNameSave}
          onPressEnter={onSiteNameSave}
          variant="borderless"
        />
      </div>
      <div className="header-actions">
        <Space size={6}>
          <Tooltip title="儲存案場設定">
            <Button aria-label="儲存案場設定" icon={<SaveOutlined />} onClick={onSaveConfig} />
          </Tooltip>
          <Tooltip title="讀取案場設定">
            <Button aria-label="讀取案場設定" icon={<FolderOpenOutlined />} onClick={onReadConfig} />
          </Tooltip>
          <Tooltip title="清空目前設定">
            <Button danger aria-label="清空目前設定" icon={<DeleteOutlined />} onClick={onClearConfig} />
          </Tooltip>
        </Space>
      </div>
      <div className="local-badge">
        <span className="pulse" /> LOCAL INSTANCE
      </div>
    </header>
  );
}
